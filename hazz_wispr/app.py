"""Menu bar app: status icon + menu, permission onboarding, and wiring of engine/store/dashboard."""

import fcntl
import os
import sys
import threading

import AppKit
import HIServices
import objc
import Quartz
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import login, server
from .engine import Engine
from .store import DATA_DIR, Store

APP_NAME = "Hazz Wispr"
ACCENT = AppKit.NSColor.colorWithSRGBRed_green_blue_alpha_(1.0, 0.353, 0.212, 1.0)  # #ff5a36

ICONS = {
    "loading": ("waveform", "Loading models…"),
    "ready": ("waveform", "Ready — hold Right Option to dictate"),
    "recording": ("waveform.circle.fill", "Listening…"),
    "processing": ("ellipsis.circle", "Transcribing…"),
    "permissions": ("exclamationmark.triangle", "Needs permissions — click to fix"),
}

PRIVACY_URLS = {
    "accessibility": "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
    "input": "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent",
}


def has_accessibility():
    return HIServices.AXIsProcessTrusted()


def has_input_monitoring():
    return Quartz.CGPreflightListenEventAccess()


class MenuDelegate(NSObject):
    """Objective-C target for menu actions and timers."""

    @objc.python_method
    def setup(self, app):
        self.app = app
        return self

    def openDashboard_(self, sender):
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(server.URL))

    def toggleCleanup_(self, sender):
        self.app.store.set_setting("cleanup", not self.app.store.setting("cleanup"))
        self.app.refresh_menu()

    def toggleLogin_(self, sender):
        login.set_enabled(not login.is_enabled())
        self.app.refresh_menu()

    def fixPermissions_(self, sender):
        key = "accessibility" if not has_accessibility() else "input"
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(PRIVACY_URLS[key]))

    def checkPermissions_(self, timer):
        if has_accessibility() and has_input_monitoring():
            timer.invalidate()
            self.app.start_engine()

    def quit_(self, sender):
        AppKit.NSApp().terminate_(None)


class HazzApp:
    def __init__(self):
        self.store = Store()
        self.engine = Engine(self.store, on_state=self._state_changed)
        self.state = "loading"
        self.delegate = MenuDelegate.alloc().init().setup(self)

        self.nsapp = AppKit.NSApplication.sharedApplication()
        self.nsapp.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)  # no Dock icon

        self.item = AppKit.NSStatusBar.systemStatusBar().statusItemWithLength_(
            AppKit.NSVariableStatusItemLength)
        self._build_menu()
        self._render()

    # --- Menu ------------------------------------------------------------------
    def _add(self, title, action=None, key=""):
        item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self.delegate)
        self.menu.addItem_(item)
        return item

    def _build_menu(self):
        self.menu = AppKit.NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(False)
        self.status_item = self._add("")
        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())
        self._add("Open Dashboard", "openDashboard:", "d")
        self.cleanup_item = self._add("AI Cleanup", "toggleCleanup:")
        self.login_item = self._add("Start at Login", "toggleLogin:")
        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())
        self._add(f"Quit {APP_NAME}", "quit:", "q")
        self.item.setMenu_(self.menu)

    def _render(self):
        symbol, label = ICONS[self.state]
        image = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(symbol, APP_NAME)
        image.setTemplate_(True)
        button = self.item.button()
        button.setImage_(image)
        button.setContentTintColor_(ACCENT if self.state == "recording" else None)
        button.setAlphaValue_(0.5 if self.state == "loading" else 1.0)

        self.status_item.setTitle_(label)
        needs_fix = self.state == "permissions"
        self.status_item.setAction_("fixPermissions:" if needs_fix else None)
        self.status_item.setEnabled_(needs_fix)

        on, off = AppKit.NSControlStateValueOn, AppKit.NSControlStateValueOff
        self.cleanup_item.setState_(on if self.store.setting("cleanup") else off)
        self.login_item.setState_(on if login.is_enabled() else off)
        self.login_item.setEnabled_(login.available())

    def refresh_menu(self):
        AppHelper.callAfter(self._render)

    def _state_changed(self, state):
        self.state = state
        self.refresh_menu()

    # --- Startup ---------------------------------------------------------------
    def start_engine(self):
        threading.Thread(target=self.engine.start, daemon=True).start()

    def run(self):
        server.serve(self)
        if has_accessibility() and has_input_monitoring():
            self.start_engine()
        else:
            # Ask macOS to show its prompts (adds Hazz Wispr to the lists), then poll.
            HIServices.AXIsProcessTrustedWithOptions({HIServices.kAXTrustedCheckOptionPrompt: True})
            Quartz.CGRequestListenEventAccess()
            self._state_changed("permissions")
            NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
                2.0, self.delegate, "checkPermissions:", None, True)
        print(f"{APP_NAME} running. Dashboard: {server.URL}")
        AppHelper.runEventLoop(installInterrupt=True)


def single_instance():
    """Hold a lock for the lifetime of the process so two copies never both paste."""
    os.makedirs(DATA_DIR, exist_ok=True)
    lock = open(os.path.join(DATA_DIR, "app.lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return None
    return lock


def main():
    lock = single_instance()
    if lock is None:
        print(f"{APP_NAME} is already running. Opening the dashboard.")
        AppKit.NSWorkspace.sharedWorkspace().openURL_(AppKit.NSURL.URLWithString_(server.URL))
        sys.exit(0)
    HazzApp().run()

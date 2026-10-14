"""Start-at-login via a per-user LaunchAgent that opens the Hazz Wispr app.

Only available when running from the .app bundle (the launcher sets HAZZ_APP_PATH),
so macOS permissions stay attached to the app rather than to Terminal.
"""

import os
import plistlib

LABEL = "com.hazz.wispr"
PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")


def app_path():
    path = os.environ.get("HAZZ_APP_PATH")
    return path if path and path.endswith(".app") and os.path.isdir(path) else None


def available():
    return app_path() is not None


def is_enabled():
    return os.path.exists(PLIST)


def set_enabled(enabled):
    if not enabled:
        if os.path.exists(PLIST):
            os.remove(PLIST)
        return
    path = app_path()
    if not path:
        raise RuntimeError("Start at login needs Hazz Wispr to be running as an app.")
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    with open(PLIST, "wb") as f:
        plistlib.dump({
            "Label": LABEL,
            "ProgramArguments": ["/usr/bin/open", "-a", path],
            "RunAtLoad": True,
        }, f)

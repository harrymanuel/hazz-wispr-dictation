"""Local dashboard: a small JSON API plus the static web app.

Security: binds to 127.0.0.1 only, rejects unexpected Host headers (DNS
rebinding) and cross-site writes (requires a JSON body and same-origin).
"""

import json
import mimetypes
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import engine, login

HOST = "127.0.0.1"
PORT = 7070
WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
URL = f"http://127.0.0.1:{PORT}"

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def make_handler(app):
    store = app.store

    def status(_):
        return {"state": app.engine.state, "last": app.engine.last}

    def get_settings(_):
        return {
            **store.settings(),
            "start_at_login": login.is_enabled(),
            "login_available": login.available(),
            "hotkey": "Right Option",
        }

    def post_settings(body):
        for key, value in body.items():
            if key == "start_at_login":
                try:
                    login.set_enabled(bool(value))
                except RuntimeError as e:
                    raise ApiError(400, str(e))
            elif key == "ollama_model":
                store.set_setting(key, str(value))
            elif key in ("cleanup", "save_history"):
                store.set_setting(key, bool(value))
            else:
                raise ApiError(400, f"Unknown setting: {key}")
        app.refresh_menu()
        return get_settings(None)

    def dictionary(_):
        return {"words": store.words(), "replacements": store.replacements()}

    def add_word(body):
        term = str(body.get("term", "")).strip()
        if not term or len(term) > 80:
            raise ApiError(400, "Enter a word or phrase (max 80 characters).")
        store.add_word(term)
        return dictionary(None)

    def add_replacement(body):
        source = str(body.get("source", "")).strip()
        target = str(body.get("target", "")).strip()
        if not source or not target or len(source) > 80 or len(target) > 200:
            raise ApiError(400, "Fill in both sides of the replacement.")
        store.add_replacement(source, target)
        return dictionary(None)

    def history(query):
        search = query.get("q", [""])[0][:100]
        return {"items": store.history(search)}

    def clear_history(_):
        store.delete_history()
        return {"ok": True}

    def models(_):
        return {"models": engine.ollama_models()}

    # (method, path regex) -> handler(body_or_query, *url_groups)
    routes = {
        ("GET", r"/api/status"): status,
        ("GET", r"/api/stats"): lambda _: store.stats(),
        ("GET", r"/api/settings"): get_settings,
        ("POST", r"/api/settings"): post_settings,
        ("GET", r"/api/models"): models,
        ("GET", r"/api/dictionary"): dictionary,
        ("POST", r"/api/dictionary/words"): add_word,
        ("DELETE", r"/api/dictionary/words/(\d+)"):
            lambda _, i: (store.delete_word(int(i)), dictionary(None))[1],
        ("POST", r"/api/dictionary/replacements"): add_replacement,
        ("DELETE", r"/api/dictionary/replacements/(\d+)"):
            lambda _, i: (store.delete_replacement(int(i)), dictionary(None))[1],
        ("GET", r"/api/history"): history,
        ("DELETE", r"/api/history"): clear_history,
        ("DELETE", r"/api/history/(\d+)"):
            lambda _, i: (store.delete_history(int(i)), {"ok": True})[1],
    }

    class Handler(BaseHTTPRequestHandler):
        server_version = "HazzWispr"

        def log_message(self, *args):
            pass  # keep the console for dictation output

        def _send(self, status, body, content_type="application/json"):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            for k, v in SECURITY_HEADERS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _trusted(self, write):
            if self.headers.get("Host") not in ALLOWED_HOSTS:
                return False
            if write:
                origin = self.headers.get("Origin")
                if origin and origin not in {f"http://{h}" for h in ALLOWED_HOSTS}:
                    return False
                if not self.headers.get("Content-Type", "").startswith("application/json"):
                    return False
            return True

        def _handle(self, method):
            if not self._trusted(write=method != "GET"):
                return self._send(403, {"error": "Forbidden"})
            url = urlparse(self.path)
            if not url.path.startswith("/api/"):
                return self._static(url.path) if method == "GET" else self._send(405, {"error": "Method not allowed"})
            for (m, pattern), fn in routes.items():
                match = re.fullmatch(pattern, url.path)
                if m == method and match:
                    try:
                        if method == "GET":
                            arg = parse_qs(url.query)
                        else:
                            length = int(self.headers.get("Content-Length") or 0)
                            arg = json.loads(self.rfile.read(length) or b"{}") if length < 100_000 else {}
                            if not isinstance(arg, dict):
                                raise ApiError(400, "Expected a JSON object.")
                        return self._send(200, fn(arg, *match.groups()))
                    except ApiError as e:
                        return self._send(e.status, {"error": str(e)})
                    except Exception as e:
                        print(f"  (dashboard error: {e})")
                        return self._send(500, {"error": "Something went wrong."})
            self._send(404, {"error": "Not found"})

        def _static(self, path):
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            full = os.path.realpath(os.path.join(WEB_DIR, name))
            if not full.startswith(os.path.realpath(WEB_DIR) + os.sep) or not os.path.isfile(full):
                return self._send(404, {"error": "Not found"})
            with open(full, "rb") as f:
                body = f.read()
            ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, body, ctype)

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

        def do_DELETE(self):
            self._handle("DELETE")

    return Handler


def serve(app):
    """Start the dashboard in a background thread. Returns False if the port is taken."""
    try:
        httpd = ThreadingHTTPServer((HOST, PORT), make_handler(app))
    except OSError as e:
        print(f"Dashboard unavailable: port {PORT} is in use ({e}).")
        return False
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return True

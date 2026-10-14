"""Local SQLite storage: settings, personal dictionary, history and usage stats.

Everything lives in ~/Library/Application Support/Hazz Wispr/hazz.db.
"""

import os
import sqlite3
import threading
import time

DATA_DIR = os.path.expanduser("~/Library/Application Support/Hazz Wispr")
DB_PATH = os.path.join(DATA_DIR, "hazz.db")

DEFAULT_SETTINGS = {
    "cleanup": True,
    "save_history": True,
    "ollama_model": "qwen2.5:3b",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS words (
    id INTEGER PRIMARY KEY, term TEXT NOT NULL UNIQUE COLLATE NOCASE, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS replacements (
    id INTEGER PRIMARY KEY, source TEXT NOT NULL UNIQUE COLLATE NOCASE,
    target TEXT NOT NULL, created REAL NOT NULL);
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY, created REAL NOT NULL, app TEXT, raw TEXT NOT NULL,
    text TEXT NOT NULL, seconds REAL NOT NULL, latency REAL NOT NULL);
CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value REAL NOT NULL);
"""


class Store:
    def __init__(self, path=DB_PATH):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _query(self, sql, args=()):
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, args).fetchall()]

    def _write(self, sql, args=()):
        with self._lock, self._db:
            return self._db.execute(sql, args).lastrowid

    # --- Settings --------------------------------------------------------------
    def settings(self):
        values = dict(DEFAULT_SETTINGS)
        for row in self._query("SELECT key, value FROM settings"):
            if row["key"] in values:
                default = DEFAULT_SETTINGS[row["key"]]
                values[row["key"]] = row["value"] == "1" if isinstance(default, bool) else row["value"]
        return values

    def setting(self, key):
        return self.settings()[key]

    def set_setting(self, key, value):
        if key not in DEFAULT_SETTINGS:
            raise KeyError(key)
        if isinstance(DEFAULT_SETTINGS[key], bool):
            value = "1" if value else "0"
        self._write("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))

    # --- Dictionary ------------------------------------------------------------
    def words(self):
        return self._query("SELECT id, term FROM words ORDER BY term COLLATE NOCASE")

    def add_word(self, term):
        return self._write(
            "INSERT INTO words (term, created) VALUES (?, ?) "
            "ON CONFLICT(term) DO UPDATE SET term = excluded.term",
            (term, time.time()),
        )

    def delete_word(self, word_id):
        self._write("DELETE FROM words WHERE id = ?", (word_id,))

    def replacements(self):
        return self._query("SELECT id, source, target FROM replacements ORDER BY source COLLATE NOCASE")

    def add_replacement(self, source, target):
        return self._write(
            "INSERT INTO replacements (source, target, created) VALUES (?, ?, ?) "
            "ON CONFLICT(source) DO UPDATE SET target = excluded.target",
            (source, target, time.time()),
        )

    def delete_replacement(self, rep_id):
        self._write("DELETE FROM replacements WHERE id = ?", (rep_id,))

    # --- History & stats -------------------------------------------------------
    def record(self, app, raw, text, seconds, latency):
        words = len(text.split())
        with self._lock, self._db:
            for key, amount in (("dictations", 1), ("words", words),
                                ("seconds", seconds), ("latency", latency)):
                self._db.execute(
                    "INSERT INTO counters (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = value + excluded.value",
                    (key, amount),
                )
        if self.setting("save_history"):
            self._write(
                "INSERT INTO history (created, app, raw, text, seconds, latency) VALUES (?, ?, ?, ?, ?, ?)",
                (time.time(), app, raw, text, seconds, latency),
            )

    def history(self, search="", limit=200):
        if search:
            return self._query(
                "SELECT * FROM history WHERE text LIKE ? OR app LIKE ? ORDER BY created DESC LIMIT ?",
                (f"%{search}%", f"%{search}%", limit),
            )
        return self._query("SELECT * FROM history ORDER BY created DESC LIMIT ?", (limit,))

    def delete_history(self, entry_id=None):
        if entry_id is None:
            self._write("DELETE FROM history")
        else:
            self._write("DELETE FROM history WHERE id = ?", (entry_id,))

    def stats(self):
        c = {r["key"]: r["value"] for r in self._query("SELECT key, value FROM counters")}
        dictations = int(c.get("dictations", 0))
        words = int(c.get("words", 0))
        spoken = c.get("seconds", 0.0)
        # Time saved vs typing at an average 40 words per minute.
        typing = words / 40 * 60
        top_apps = self._query(
            "SELECT app, COUNT(*) AS count FROM history WHERE app IS NOT NULL "
            "GROUP BY app ORDER BY count DESC LIMIT 5"
        )
        return {
            "dictations": dictations,
            "words": words,
            "seconds_saved": max(0.0, typing - spoken - c.get("latency", 0.0)),
            "avg_latency": c.get("latency", 0.0) / dictations if dictations else None,
            "top_apps": top_apps,
        }

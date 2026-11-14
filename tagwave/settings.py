"""User settings persisted as JSON in %APPDATA%\\Tagwave\\settings.json."""

from __future__ import annotations

import json
import os
import threading

from . import paths

DEFAULTS = {
    "language": "en",              # en | fa
    "theme": "dark",               # dark | light | system
    "id3Version": "keep",          # keep | 3 | 4
    "id3v1": "keep",               # keep | remove | write
    "preserveMtime": False,
    "verifyOnSave": True,
    "verifyConversions": True,
    "onlineEnabled": True,
    "onlineProviders": ["musicbrainz", "itunes", "deezer"],
    "confirmLossy": True,
    "lastOpenDir": "",
    "lastImageDir": "",
    "lastExportDir": "",
    "export": {"target": "flac", "quality": {}, "outputMode": "same", "outputDir": "",
               "overwrite": "rename", "flacLevel": 8, "addToList": False},
    "renamePattern": "{track} - {artist} - {title}",
    "renameHistory": [],
    "parsePattern": "{artist} - {title}",
    "volume": 0.8,
    "window": {"width": 1360, "height": 880, "maximized": False},
    "listColumns": None,
}

_ALLOWED = {
    "language": {"en", "fa"}, "theme": {"dark", "light", "system"},
    "id3Version": {"keep", "3", "4"}, "id3v1": {"keep", "remove", "write"},
}


class Settings:
    def __init__(self, path: str | None = None):
        self.path = path or os.path.join(paths.data_dir(), "settings.json")
        self._lock = threading.Lock()
        self.data = json.loads(json.dumps(DEFAULTS))
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                self._merge(stored)
        except (OSError, ValueError):
            pass

    def _merge(self, patch: dict) -> None:
        for k, v in patch.items():
            if k not in DEFAULTS:
                continue
            if k in _ALLOWED and v not in _ALLOWED[k]:
                continue
            if isinstance(DEFAULTS[k], dict) and isinstance(v, dict):
                merged = dict(self.data.get(k) or {})
                merged.update({kk: vv for kk, vv in v.items()})
                self.data[k] = merged
            elif DEFAULTS[k] is None or isinstance(v, type(DEFAULTS[k])) or (
                    isinstance(DEFAULTS[k], float) and isinstance(v, int)):
                self.data[k] = v

    def get(self, key: str):
        with self._lock:
            return json.loads(json.dumps(self.data.get(key)))

    def snapshot(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self.data))

    def update(self, patch: dict) -> dict:
        with self._lock:
            self._merge(patch or {})
            self._save()
            return json.loads(json.dumps(self.data))

    def _save(self) -> None:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

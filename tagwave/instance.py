"""Single-instance support.

When several files are opened from Explorer at once, Windows starts one process per
file. The first one becomes the app; the others hand their paths over through a named
pipe (authenticated with a per-user random key, JSON only, no pickle) and exit.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import secrets
import threading
import time
from multiprocessing.connection import Client, Listener

from . import paths

ERROR_ALREADY_EXISTS = 183


def _ids() -> tuple[str, str]:
    user = (os.environ.get("USERDOMAIN", "") + "\\" + os.environ.get("USERNAME", "user")).lower()
    h = hashlib.sha1(user.encode("utf-8")).hexdigest()[:16]
    return "Local\\Tagwave-%s" % h, r"\\.\pipe\tagwave-%s" % h


def _authkey() -> bytes:
    p = os.path.join(paths.data_dir(), "ipc.key")
    try:
        with open(p, "rb") as f:
            key = f.read()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_bytes(32)
    with open(p, "wb") as f:
        f.write(key)
    return key


class SingleInstance:
    def __init__(self):
        self.mutex_name, self.pipe = _ids()
        self._mutex = None
        self._listener = None

    def acquire(self) -> bool:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateMutexW.restype = ctypes.c_void_p
        self._mutex = k32.CreateMutexW(None, False, self.mutex_name)
        return ctypes.get_last_error() != ERROR_ALREADY_EXISTS

    def send(self, file_paths: list, timeout: float = 15.0) -> bool:
        try:
            ctypes.windll.user32.AllowSetForegroundWindow(-1)   # let the main window come to front
        except Exception:
            pass
        payload = json.dumps({"paths": [os.path.abspath(p) for p in file_paths]}).encode("utf-8")
        key = _authkey()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                conn = Client(self.pipe, family="AF_PIPE", authkey=key)
                try:
                    conn.send_bytes(payload)
                finally:
                    conn.close()
                return True
            except (OSError, EOFError):
                time.sleep(0.15)
        return False

    def serve(self, on_message) -> None:
        self._listener = Listener(self.pipe, family="AF_PIPE", authkey=_authkey())

        def loop():
            while True:
                try:
                    conn = self._listener.accept()
                except Exception:
                    if self._listener is None:
                        return
                    continue
                try:
                    data = json.loads(conn.recv_bytes(1 << 20).decode("utf-8"))
                    if isinstance(data, dict) and isinstance(data.get("paths"), list):
                        on_message([p for p in data["paths"] if isinstance(p, str)])
                except Exception:
                    pass
                finally:
                    conn.close()

        threading.Thread(target=loop, name="ipc", daemon=True).start()

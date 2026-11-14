"""Content-addressed store for images (covers, crops, downloads, spectrograms).

Each blob lives in a temp file named by its SHA-1, so identical covers are shared
and a blob id can never point at the wrong bytes.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import threading

from . import paths
from .core import images


class BlobStore:
    def __init__(self, root: str | None = None):
        base = root or paths.temp_root()
        self._cleanup_stale(base)
        self.dir = os.path.join(base, "session-%d" % os.getpid(), "blobs")
        os.makedirs(self.dir, exist_ok=True)
        self._meta: dict = {}
        self._lock = threading.Lock()

    @staticmethod
    def _cleanup_stale(base: str) -> None:
        """Remove leftovers of sessions whose process no longer runs."""
        try:
            for name in os.listdir(base):
                if not name.startswith("session-"):
                    continue
                try:
                    pid = int(name.split("-", 1)[1])
                except ValueError:
                    continue
                if pid == os.getpid() or _pid_alive(pid):
                    continue
                shutil.rmtree(os.path.join(base, name), ignore_errors=True)
        except OSError:
            pass

    def path(self, blob_id: str) -> str:
        if not blob_id or not all(c in "0123456789abcdef" for c in blob_id) or len(blob_id) != 40:
            raise KeyError(blob_id)
        return os.path.join(self.dir, blob_id)

    def put(self, data: bytes) -> str:
        blob_id = hashlib.sha1(data).hexdigest()
        p = self.path(blob_id)
        if not os.path.exists(p):
            tmp = p + ".%d.tmp" % threading.get_ident()
            with open(tmp, "wb") as f:
                f.write(data)
            try:
                os.replace(tmp, p)
            except OSError:
                if os.path.exists(tmp):
                    os.remove(tmp)
        return blob_id

    def exists(self, blob_id: str) -> bool:
        try:
            return os.path.exists(self.path(blob_id))
        except KeyError:
            return False

    def read(self, blob_id: str) -> bytes:
        with open(self.path(blob_id), "rb") as f:
            return f.read()

    def meta(self, blob_id: str) -> dict:
        with self._lock:
            m = self._meta.get(blob_id)
        if m is None:
            data = self.read(blob_id)
            im = images.image_meta(data)
            m = {"mime": im.mime, "width": im.width, "height": im.height, "size": len(data)}
            with self._lock:
                self._meta[blob_id] = m
        return dict(m)

    def info(self, blob_id: str) -> dict:
        m = self.meta(blob_id)
        m["blob"] = blob_id
        return m

    def thumbnail(self, blob_id: str, size: int) -> tuple[str, str]:
        size = max(32, min(int(size), 1024))
        for ext, mime in ((".jpg", images.JPEG), (".png", images.PNG)):
            p = self.path(blob_id) + "_%d%s" % (size, ext)
            if os.path.exists(p):
                return p, mime
        data, mime = images.thumbnail(self.read(blob_id), size)
        p = self.path(blob_id) + "_%d%s" % (size, ".png" if mime == images.PNG else ".jpg")
        tmp = p + ".%d.tmp" % threading.get_ident()
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, p)
        return p, mime

    def close(self) -> None:
        shutil.rmtree(os.path.dirname(self.dir), ignore_errors=True)


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":  # pragma: no cover
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    code = ctypes.c_ulong()
    try:
        ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


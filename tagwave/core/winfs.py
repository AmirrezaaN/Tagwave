"""Small Windows filesystem helpers (no-ops on other platforms)."""

from __future__ import annotations

import os
import sys
import time

from .errors import FileInUseError

FILE_ATTRIBUTE_READONLY = 0x1


def is_read_only(st: os.stat_result) -> bool:
    attrs = getattr(st, "st_file_attributes", None)
    if attrs is not None:
        return bool(attrs & FILE_ATTRIBUTE_READONLY)
    return not (st.st_mode & 0o200)


def replace_with_retry(src: str, dst: str, attempts: int = 12, delay: float = 0.25) -> None:
    """os.replace, retrying while another process briefly holds the file open."""
    for i in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == attempts - 1:
                raise FileInUseError("The file is in use by another program.") from None
            time.sleep(delay)


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _CreateFileW = _k32.CreateFileW
    _CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _CreateFileW.restype = wintypes.HANDLE
    _SetFileTime = _k32.SetFileTime
    _SetFileTime.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
                             ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    _CloseHandle = _k32.CloseHandle
    _SetFileAttributesW = _k32.SetFileAttributesW
    _SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _INVALID = wintypes.HANDLE(-1).value

    def _filetime(ns: int) -> wintypes.FILETIME:
        v = ns // 100 + 116444736000000000
        return wintypes.FILETIME(v & 0xFFFFFFFF, v >> 32)

    def restore_metadata(path: str, st: os.stat_result) -> None:
        """Put back the original creation time and attributes after a replace."""
        try:
            birth = getattr(st, "st_birthtime_ns", None) or st.st_ctime_ns
            h = _CreateFileW(path, 0x0100, 0x7, None, 3, 0x02000000, None)  # FILE_WRITE_ATTRIBUTES
            if h and h != _INVALID:
                try:
                    ft = _filetime(birth)
                    _SetFileTime(h, ctypes.byref(ft), None, None)
                finally:
                    _CloseHandle(h)
            attrs = getattr(st, "st_file_attributes", None)
            if attrs:
                _SetFileAttributesW(path, attrs & 0x27)  # readonly|hidden|system|archive
        except Exception:
            pass
else:  # pragma: no cover
    def restore_metadata(path: str, st: os.stat_result) -> None:
        pass

"""The native desktop window (pywebview + Microsoft Edge WebView2)."""

from __future__ import annotations

import ctypes
import os
import sys

import webview
from webview.dom import DOMEventHandler

from . import APP_NAME
from .core import audiofile

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff")


def _colorref(hex_color: str) -> int | None:
    h = (hex_color or "").lstrip("#")
    if len(h) != 6:
        return None
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return None
    return r | (g << 8) | (b << 16)


def _work_area() -> tuple[int, int] | None:
    """Usable desktop size (without the taskbar) in logical pixels."""
    try:
        from ctypes import wintypes
        rect = wintypes.RECT()
        ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0)  # SPI_GETWORKAREA
        dpi = ctypes.windll.user32.GetDpiForSystem() or 96
        f = dpi / 96.0
        return int((rect.right - rect.left) / f), int((rect.bottom - rect.top) / f)
    except Exception:
        return None


class Native:
    def __init__(self, api, url: str, debug: bool = False):
        self.api = api
        self._force_close = False
        s = api.settings.get("window") or {}
        dark = api.settings.get("theme") != "light"
        width, height = int(s.get("width") or 1360), int(s.get("height") or 880)
        min_w, min_h = 960, 600
        area = _work_area()
        if area:
            # Never open larger than the screen (small laptops, high display scaling).
            width = max(min(width, int(area[0] * 0.94)), min(min_w, area[0]))
            height = max(min(height, int(area[1] * 0.94)), min(min_h, area[1]))
            min_w, min_h = min(min_w, area[0]), min(min_h, area[1])
        self.window = webview.create_window(
            APP_NAME, url,
            width=width, height=height,
            min_size=(min_w, min_h), maximized=bool(s.get("maximized")),
            background_color="#0d0e12" if dark else "#f6f7fb",
            text_select=False, zoomable=False,
        )
        self.window.events.closing += self._on_closing
        self.window.events.loaded += self._on_loaded
        self.window.events.shown += lambda: self.set_theme(dark, "#0d0e12" if dark else "#f6f7fb")
        self._drop_handler = DOMEventHandler(self._on_drop, True, True)
        self._drop_registered = False

    # ------------------------------------------------------------- events
    def _on_loaded(self):
        doc = self.window.dom.document
        if self._drop_registered:
            try:
                doc.events.drop -= self._drop_handler
            except Exception:
                pass
        doc.events.drop += self._drop_handler
        self._drop_registered = True

    def _on_drop(self, e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        dropped = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        audio = [p for p in dropped if os.path.isdir(p) or audiofile.is_supported_path(p)]
        pics = [p for p in dropped if p.lower().endswith(IMAGE_EXTS)]
        if audio:
            self.api.add_paths(audio, origin="drop")
        elif pics:
            self.api.bus.publish("images.dropped", {"paths": pics})
        elif dropped:
            self.api.bus.publish("drop.unsupported", {"count": len(dropped)})

    def _on_closing(self):
        if not self._force_close and self.api.dirty:
            self.api.bus.publish("window.closeRequested", {})
            return False
        try:
            maximized = bool(self._is_maximized())
            data = {"maximized": maximized}
            if not maximized and self.window.width > 400:
                data.update(width=int(self.window.width), height=int(self.window.height))
            current = self.api.settings.get("window") or {}
            current.update(data)
            self.api.settings.update({"window": current})
        except Exception:
            pass
        return True

    def close_now(self):
        self._force_close = True
        self.window.destroy()

    # ------------------------------------------------------------ dialogs
    def open_files(self, types: str, initial: str = "", multiple: bool = True) -> list:
        res = self.window.create_file_dialog(webview.FileDialog.OPEN, directory=initial or "",
                                             allow_multiple=multiple, file_types=(types, "All files (*.*)"))
        return list(res) if res else []

    def pick_folder(self, initial: str = "") -> str | None:
        res = self.window.create_file_dialog(webview.FileDialog.FOLDER, directory=initial or "")
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    def save_file(self, name: str, types: str, initial: str = "") -> str | None:
        res = self.window.create_file_dialog(webview.FileDialog.SAVE, directory=initial or "",
                                             save_filename=name, file_types=(types,))
        if not res:
            return None
        return res[0] if isinstance(res, (list, tuple)) else res

    # -------------------------------------------------------- appearance
    def _hwnd(self) -> int | None:
        try:
            return int(self.window.native.Handle.ToInt64())
        except Exception:
            return None

    def _is_maximized(self) -> bool:
        hwnd = self._hwnd()
        return bool(hwnd and ctypes.windll.user32.IsZoomed(hwnd))

    def set_theme(self, dark: bool, background: str = "") -> None:
        hwnd = self._hwnd()
        if not hwnd or sys.platform != "win32":
            return
        dwm = ctypes.windll.dwmapi

        def attr(a, v):
            val = ctypes.c_int(v)
            dwm.DwmSetWindowAttribute(hwnd, a, ctypes.byref(val), ctypes.sizeof(val))

        attr(20, 1 if dark else 0)               # immersive dark title bar
        bg = _colorref(background)
        if bg is not None:
            attr(35, bg)                         # caption colour (Windows 11)
            attr(34, bg)                         # border colour
            attr(36, 0x00F2F2F2 if dark else 0x00222222)   # caption text

    def focus(self) -> None:
        try:
            self.window.restore()
            self.window.show()
            hwnd = self._hwnd()
            if hwnd:
                u = ctypes.windll.user32
                if u.IsIconic(hwnd):
                    u.ShowWindow(hwnd, 9)
                u.SetForegroundWindow(hwnd)
        except Exception:
            pass

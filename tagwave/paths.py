"""Locations of bundled resources and per-user data."""

from __future__ import annotations

import os
import sys

from . import APP_NAME


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> str:
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ui_dir() -> str:
    if is_frozen():
        return os.path.join(resource_root(), "ui")
    return os.path.join(resource_root(), "ui", "dist")


def icon_path() -> str | None:
    for p in (os.path.join(resource_root(), "assets", "tagwave.ico"),
              os.path.join(resource_root(), "packaging", "tagwave.ico")):
        if os.path.exists(p):
            return p
    return None


def data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = os.path.join(base, APP_NAME)
    os.makedirs(d, exist_ok=True)
    return d


def temp_root() -> str:
    base = os.environ.get("TEMP") or os.environ.get("TMP") or data_dir()
    return os.path.join(base, "Tagwave")

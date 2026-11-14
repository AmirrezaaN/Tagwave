"""Locating and running the bundled FFmpeg / FFprobe binaries."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from functools import lru_cache

# Prevents a console window from flashing when the GUI app spawns ffmpeg.
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


class FFmpegError(RuntimeError):
    pass


def _candidate_dirs():
    env = os.environ.get("TAGWAVE_FFMPEG_DIR")
    if env:
        yield env
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        yield os.path.join(exe_dir, "bin")
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            yield os.path.join(meipass, "bin")
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    yield os.path.join(project_root, "vendor", "bin")


@lru_cache(maxsize=None)
def find_tool(name: str) -> str | None:
    exe = name + (".exe" if sys.platform == "win32" else "")
    for d in _candidate_dirs():
        p = os.path.join(d, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


def ffmpeg_path() -> str:
    p = find_tool("ffmpeg")
    if not p:
        raise FFmpegError("FFmpeg was not found.")
    return p


def ffprobe_path() -> str:
    p = find_tool("ffprobe")
    if not p:
        raise FFmpegError("FFprobe was not found.")
    return p


def available() -> bool:
    return bool(find_tool("ffmpeg") and find_tool("ffprobe"))


def run(args: list[str], *, timeout: float | None = None, binary: bool = False) -> subprocess.CompletedProcess:
    """Run a command without a console window and capture its output."""
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
        text=not binary,
        encoding=None if binary else "utf-8",
        errors=None if binary else "replace",
    )


def popen(args: list[str], **kw) -> subprocess.Popen:
    kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("creationflags", CREATE_NO_WINDOW)
    return subprocess.Popen(args, **kw)


def probe(path: str) -> dict:
    """Return ffprobe's JSON description of the first audio stream and the format."""
    res = run(
        [ffprobe_path(), "-v", "error", "-print_format", "json", "-show_format",
         "-show_streams", "-select_streams", "a:0", path],
        timeout=60,
    )
    if res.returncode != 0:
        raise FFmpegError(res.stderr.strip() or "ffprobe failed")
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams") or []
    if not streams:
        raise FFmpegError("No audio stream found.")
    return {"stream": streams[0], "format": data.get("format", {})}


def _md5(args: list[str], timeout: float) -> str:
    res = run(args, timeout=timeout)
    if res.returncode != 0:
        raise FFmpegError(res.stderr.strip() or "ffmpeg failed")
    for line in res.stdout.splitlines():
        if line.startswith("MD5="):
            return line[4:].strip()
    raise FFmpegError("ffmpeg produced no checksum")


def audio_packet_md5(path: str, timeout: float = 600) -> str:
    """MD5 of the compressed audio packets (independent of tags/container metadata)."""
    return _md5([ffmpeg_path(), "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0",
                 "-c", "copy", "-f", "md5", "-"], timeout)


def pcm_md5(path: str, sample_fmt: str = "s32le", timeout: float = 900) -> str:
    """MD5 of the fully decoded PCM audio, used to prove bit-perfect conversions."""
    return _md5([ffmpeg_path(), "-v", "error", "-nostdin", "-i", path, "-map", "0:a:0",
                 "-c:a", "pcm_" + sample_fmt, "-f", "md5", "-"], timeout)

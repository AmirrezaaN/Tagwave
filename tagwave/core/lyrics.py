"""LRC (synchronised lyrics) parsing and formatting."""

from __future__ import annotations

import re

_TIME = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")
_META = re.compile(r"^\[(ar|ti|al|au|by|length|offset|re|ve|#):(.*)\]\s*$", re.IGNORECASE)


def _to_ms(m: re.Match) -> int:
    minutes, seconds, frac = int(m.group(1)), int(m.group(2)), m.group(3)
    ms = 0
    if frac:
        ms = int(frac.ljust(3, "0")[:3]) if len(frac) <= 3 else int(frac[:3])
    return (minutes * 60 + seconds) * 1000 + ms


def parse_lrc(text: str) -> tuple[list[tuple[int, str]], dict]:
    """Return ([(ms, line), ...] sorted by time, metadata)."""
    lines: list[tuple[int, str]] = []
    meta: dict = {}
    body = []
    for raw in (text or "").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        mm = _META.match(raw)
        if mm and not _TIME.match(raw):
            meta[mm.group(1).lower()] = mm.group(2).strip()
        else:
            body.append(raw)
    try:
        offset = int(meta.get("offset", "0").replace("+", ""))  # applies to the whole file
    except ValueError:
        offset = 0
    for raw in body:
        stamps = []
        pos = 0
        while True:
            m = _TIME.match(raw, pos)
            if not m:
                break
            stamps.append(_to_ms(m))
            pos = m.end()
        if stamps:
            line = raw[pos:].strip()
            for ms in stamps:
                lines.append((max(0, ms - offset), line))
    lines.sort(key=lambda x: x[0])
    return lines, meta


def is_synced(text: str) -> bool:
    lines, _ = parse_lrc(text)
    return len(lines) > 0


def format_time(ms: int) -> str:
    ms = max(0, int(ms))
    minutes, rem = divmod(ms, 60000)
    seconds, millis = divmod(rem, 1000)
    return "[%02d:%02d.%02d]" % (minutes, seconds, millis // 10)


def format_lrc(lines: list[tuple[int, str]], meta: dict | None = None) -> str:
    out = []
    for k, v in (meta or {}).items():
        if k != "offset":
            out.append("[%s:%s]" % (k, v))
    for ms, line in lines:
        out.append(format_time(ms) + line)
    return "\n".join(out)

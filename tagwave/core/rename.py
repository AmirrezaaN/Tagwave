"""Rename files from tags, and fill tags from file names."""

from __future__ import annotations

import os
import re
import secrets

from .errors import TagwaveError

PLACEHOLDERS = ("title", "artist", "album", "albumartist", "year", "date", "genre", "track",
                "tracktotal", "disc", "disctotal", "composer", "filename")
PARSE_FIELDS = ("title", "artist", "album", "albumartist", "date", "genre", "track", "tracktotal",
                "disc", "disctotal", "composer", "skip")

_TOKEN = re.compile(r"\{(\w+)(?::(\d))?\}")
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *("COM%d" % i for i in range(1, 10)),
             *("LPT%d" % i for i in range(1, 10))}


class PatternError(TagwaveError):
    code = "invalid-pattern"


def check_pattern(pattern: str, allowed=PLACEHOLDERS) -> list:
    tokens = _TOKEN.findall(pattern or "")
    if not tokens:
        raise PatternError("The pattern needs at least one {field}.")
    for name, _pad in tokens:
        if name not in allowed:
            raise PatternError("Unknown field {%s}." % name, field=name)
    return tokens


def sanitize(name: str) -> str:
    name = _INVALID.sub("_", name)
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip(" .")
    if name.split(".")[0].upper() in _RESERVED:
        name = "_" + name
    return name[:200]


def format_name(pattern: str, fields: dict, stem: str) -> str:
    check_pattern(pattern)

    def repl(m):
        key, pad = m.group(1), m.group(2)
        if key == "filename":
            return stem
        if key == "year":
            value = (fields.get("date") or "")[:4]
        else:
            value = fields.get(key) or ""
        value = str(value).strip()
        if key in ("track", "disc", "tracktotal", "disctotal") and value.isdigit():
            width = int(pad) if pad else (2 if key == "track" else 1)
            value = value.zfill(width)
        return value.replace("/", "-").replace("\\", "-").replace("\x00", "") or "\x00"

    raw = _TOKEN.sub(repl, pattern)
    # Remove the separators that belonged to empty fields (never touching the values):
    # "01 - \0 - Title" -> "01 - Title", "\0 - Artist" -> "Artist", "A (\0)" -> "A"
    raw = re.sub(r"^(\x00[\s\-–_.,]*)+", "", raw)
    raw = re.sub(r"[\s\-–_.,]*\x00", "", raw)
    raw = re.sub(r"\(\s*\)|\[\s*\]", "", raw)
    return sanitize(raw)


def preview(items: list, pattern: str) -> list:
    """items: [{'id', 'path', 'fields'}] -> [{'id', 'path', 'newPath', 'newName', 'status'}]."""
    check_pattern(pattern)
    out = []
    targets: dict = {}
    for it in items:
        path = it["path"]
        d, name = os.path.split(path)
        stem, ext = os.path.splitext(name)
        new_stem = format_name(pattern, it.get("fields") or {}, stem)
        if not new_stem:
            out.append({"id": it["id"], "path": path, "newPath": path, "newName": name, "status": "empty"})
            continue
        new_name = new_stem + ext
        new_path = os.path.join(d, new_name)
        status = "same" if new_path == path else "ok"
        key = os.path.normcase(new_path)
        if status == "ok" and key in targets:
            status = "conflict"
            out[targets[key]]["status"] = "conflict"
        targets.setdefault(key, len(out))
        out.append({"id": it["id"], "path": path, "newPath": new_path, "newName": new_name, "status": status})
    # A target that already exists on disk is fine only if that file is itself
    # being renamed away in this batch (e.g. two files swapping names).
    moving = {os.path.normcase(p["path"]) for p in out if p["status"] == "ok"}
    for p in out:
        if p["status"] != "ok":
            continue
        key = os.path.normcase(p["newPath"])
        if key != os.path.normcase(p["path"]) and os.path.exists(p["newPath"]) and key not in moving:
            p["status"] = "exists"
    return out


def apply(plan: list) -> list:
    """Rename every 'ok' entry. Two-phase so that swapping names between files works.

    Returns [{'id', 'path', 'newPath', 'ok', 'error'}].
    """
    todo = [p for p in plan if p["status"] == "ok"]
    staged = []
    results = {p["id"]: {"id": p["id"], "path": p["path"], "newPath": p["path"], "ok": False,
                         "error": None if p["status"] in ("ok", "same") else p["status"]}
               for p in plan}
    for p in todo:
        d = os.path.dirname(p["path"])
        tmp = os.path.join(d, ".tagwave-rename-%s.tmp" % secrets.token_hex(6))
        try:
            os.rename(p["path"], tmp)
            staged.append((p, tmp))
        except OSError as exc:
            results[p["id"]]["error"] = "file-in-use" if isinstance(exc, PermissionError) else "rename-failed"
    for p, tmp in staged:
        try:
            if os.path.exists(p["newPath"]):
                raise FileExistsError(p["newPath"])
            os.rename(tmp, p["newPath"])
            results[p["id"]].update(ok=True, newPath=p["newPath"])
        except OSError:
            os.rename(tmp, p["path"])
            results[p["id"]]["error"] = "exists" if os.path.exists(p["newPath"]) else "rename-failed"
    for p in plan:
        if p["status"] == "same":
            results[p["id"]]["ok"] = True
    return [results[p["id"]] for p in plan]


def parse_filename(pattern: str, stem: str) -> dict | None:
    """'{track} - {artist} - {title}' + '03 - A - B' -> {'track': '03', ...}."""
    tokens = check_pattern(pattern, PARSE_FIELDS)
    parts = _TOKEN.split(pattern)
    regex = "^"
    names = []
    i = 0
    while i < len(parts):
        regex += re.escape(parts[i])
        if i + 1 < len(parts):
            name = parts[i + 1]
            last = i + 3 >= len(parts) or all(not x for x in parts[i + 3:])
            if name in ("track", "tracktotal", "disc", "disctotal"):
                regex += r"\s*(\d+)\s*"
            else:
                regex += "(.+)" if last else "(.+?)"
            names.append(name)
        i += 3
    regex += "$"
    m = re.match(regex, stem.strip())
    if not m:
        return None
    out = {}
    for name, value in zip(names, m.groups()):
        if name != "skip":
            out[name] = value.strip()
    if "track" in out and out["track"].isdigit():
        out["track"] = str(int(out["track"]))
    del tokens
    return out

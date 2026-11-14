"""Format-independent tag model shared by all tag handlers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..errors import TagwaveError

FIELD_KEYS = [
    "title", "artist", "album", "albumartist", "date", "genre",
    "track", "tracktotal", "disc", "disctotal",
    "composer", "lyricist", "conductor", "comment", "lyrics", "bpm",
    "publisher", "copyright", "encodedby", "isrc", "grouping", "compilation",
]

# Separator used to show multi-valued tags as one editable string.
MULTI_SEP = "; "

PICTURE_TYPES = {
    0: "Other", 1: "File icon", 2: "Other file icon", 3: "Front cover", 4: "Back cover",
    5: "Leaflet page", 6: "Media", 7: "Lead artist", 8: "Artist", 9: "Conductor",
    10: "Band", 11: "Composer", 12: "Lyricist", 13: "Recording location",
    14: "During recording", 15: "During performance", 16: "Video capture",
    17: "Bright coloured fish", 18: "Illustration", 19: "Band logo", 20: "Publisher logo",
}


class TagError(TagwaveError, ValueError):
    """A user-correctable problem with tag values. `code` is used for UI translation."""

    def __init__(self, message: str, code: str = "invalid-tag", field: str | None = None):
        super().__init__(message, code, field=field)
        self.field = field


_DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2}([T ]\d{2}(:\d{2}(:\d{2})?)?)?)?)?$")
_NUM_FIELDS = ("track", "tracktotal", "disc", "disctotal")


def validate_fields(fields: dict) -> None:
    """Reject values that some formats can't store, so every format behaves the same."""
    for key, value in fields.items():
        value = "" if value is None else str(value).strip()
        if not value:
            continue
        if key == "date" and not _DATE_RE.match(value):
            raise TagError("Year must look like 2024 or 2024-05-31.", "invalid-date", key)
        if key in _NUM_FIELDS and not value.isdigit():
            raise TagError("Track and disc numbers must be whole numbers.", "invalid-number", key)
        if key == "bpm":
            try:
                if float(value) < 0:
                    raise ValueError
            except ValueError:
                raise TagError("BPM must be a number.", "invalid-bpm", key) from None


@dataclass
class Picture:
    type: int
    mime: str
    desc: str
    data: bytes


@dataclass
class TagSnapshot:
    fields: dict
    custom: list            # [[key, value], ...] in file order
    pictures: list          # [Picture, ...]
    tag_format: str


@dataclass
class TagChanges:
    fields: dict = field(default_factory=dict)      # only changed keys; "" deletes
    custom: list | None = None                       # full desired list, or None = untouched
    pictures: list | None = None                     # full desired list, or None = untouched

    def is_empty(self) -> bool:
        return not self.fields and self.custom is None and self.pictures is None


@dataclass
class SaveOptions:
    id3_version: str = "keep"    # "keep" | "3" | "4"
    id3v1: str = "keep"          # "keep" | "remove" | "write"


def empty_fields() -> dict:
    return {k: "" for k in FIELD_KEYS}


def split_pair(value: str) -> tuple[str, str]:
    """'3/12' -> ('3', '12'); '3' -> ('3', '')."""
    value = (value or "").strip()
    if "/" in value:
        a, b = value.split("/", 1)
        return a.strip(), b.strip()
    return value, ""


def clean_number(value: str) -> str:
    """Normalise '03' style numbers but keep whatever the user typed if non-numeric."""
    value = (value or "").strip()
    if value.isdigit():
        return str(int(value))
    return value


def join_values(values) -> str:
    out = []
    for v in values:
        s = str(v)
        if s != "":
            out.append(s)
    return MULTI_SEP.join(out)


def truthy(value: str) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def custom_diff(old: list, new: list, normalize=lambda k: k):
    """Compare custom-field lists. Returns (to_set: {key: value}, to_delete: [key])."""
    old_map: dict = {}
    for k, v in old:
        old_map[normalize(k)] = v
    new_map: dict = {}
    for k, v in new:
        k = (k or "").strip()
        if not k:
            continue
        new_map[normalize(k)] = (k, "" if v is None else str(v))
    to_set = {}
    for nk, (k, v) in new_map.items():
        if v == "":
            continue
        if old_map.get(nk) != v:
            to_set[k] = v
    to_delete = [k for k in old_map if k not in new_map or new_map[k][1] == ""]
    return to_set, to_delete


def ordered_pictures(pictures: list) -> list:
    """Front cover first, keeping the relative order of everything else."""
    front = [p for p in pictures if p.type == 3]
    rest = [p for p in pictures if p.type != 3]
    return front + rest


class TagHandler:
    tag_format = ""
    picture_types = True      # supports picture type field
    picture_desc = True       # supports picture description

    def __init__(self, audio):
        self.audio = audio

    def read(self) -> TagSnapshot:  # pragma: no cover - abstract
        raise NotImplementedError

    def apply(self, changes: TagChanges) -> list:  # pragma: no cover - abstract
        raise NotImplementedError

    def save(self, filename: str, opts: SaveOptions) -> None:
        self.audio.save(filename)

    def merged_fields(self, changes: TagChanges) -> dict:
        current = self.read().fields
        merged = dict(current)
        for k, v in changes.fields.items():
            merged[k] = "" if v is None else str(v)
        return merged

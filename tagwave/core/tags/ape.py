"""APEv2 tags (Monkey's Audio, WavPack, Musepack, OptimFROG)."""

from __future__ import annotations

from mutagen.apev2 import BINARY, TEXT, APEValue

from .. import images
from .base import (FIELD_KEYS, Picture, TagChanges, TagError, TagHandler, TagSnapshot,
                   clean_number, custom_diff, empty_fields, join_values, ordered_pictures,
                   split_pair, truthy)

KEYS = {
    "title": ["Title"], "artist": ["Artist"], "album": ["Album"],
    "albumartist": ["Album Artist", "AlbumArtist"], "date": ["Year"], "genre": ["Genre"],
    "track": ["Track"], "disc": ["Disc"], "composer": ["Composer"], "lyricist": ["Lyricist"],
    "conductor": ["Conductor"], "comment": ["Comment"], "lyrics": ["Lyrics"], "bpm": ["BPM"],
    "publisher": ["Publisher", "Label"], "copyright": ["Copyright"],
    "encodedby": ["EncodedBy"], "isrc": ["ISRC"], "grouping": ["Grouping"],
    "compilation": ["Compilation"],
}

COVER_KEYS = {
    0: "Cover Art (Other)", 1: "Cover Art (Icon)", 2: "Cover Art (Other Icon)",
    3: "Cover Art (Front)", 4: "Cover Art (Back)", 5: "Cover Art (Leaflet)",
    6: "Cover Art (Media)", 7: "Cover Art (Lead Artist)", 8: "Cover Art (Artist)",
    9: "Cover Art (Conductor)", 10: "Cover Art (Band)", 11: "Cover Art (Composer)",
    12: "Cover Art (Lyricist)", 13: "Cover Art (Recording Location)",
    14: "Cover Art (During Recording)", 15: "Cover Art (During Performance)",
    16: "Cover Art (Video Capture)", 17: "Cover Art (Fish)", 18: "Cover Art (Illustration)",
    19: "Cover Art (Band Logotype)", 20: "Cover Art (Publisher Logotype)",
}
_COVER_TYPE = {v.lower(): k for k, v in COVER_KEYS.items()}


def _is_cover_key(key: str) -> bool:
    return key.lower().startswith("cover art (")


class APEHandler(TagHandler):
    tag_format = "APEv2"
    picture_desc = False

    def __init__(self, audio):
        super().__init__(audio)
        if audio.tags is None:
            audio.add_tags()
        self.tags = audio.tags

    def _active(self) -> dict:
        lower = {k.lower() for k in self.tags.keys()}
        return {f: next((c for c in cands if c.lower() in lower), cands[0]) for f, cands in KEYS.items()}

    def _text(self, key) -> str | None:
        if key not in self.tags:
            return None
        v = self.tags[key]
        if v.kind != TEXT:
            return None
        return join_values(list(v))

    def _custom_current(self, active) -> list:
        used = {k.lower() for k in active.values()}
        out = []
        for key in self.tags.keys():
            if key.lower() in used or _is_cover_key(key):
                continue
            text = self._text(key)
            if text is not None:
                out.append([key, text])
        return out

    def read(self) -> TagSnapshot:
        active = self._active()
        f = empty_fields()
        for field, key in active.items():
            text = self._text(key)
            if text:
                f[field] = text
        f["track"], f["tracktotal"] = split_pair(f["track"])
        f["disc"], f["disctotal"] = split_pair(f["disc"])
        f["compilation"] = "1" if truthy(f["compilation"]) else ""
        pics = []
        for key in self.tags.keys():
            if not _is_cover_key(key):
                continue
            v = self.tags[key]
            if v.kind != BINARY:
                continue
            raw = bytes(v.value)
            nul = raw.find(b"\x00")
            data = raw[nul + 1:] if 0 <= nul < 256 else raw
            if not data:
                continue
            pics.append(Picture(_COVER_TYPE.get(key.lower(), 0),
                                images.sniff_mime(data) or "image/jpeg", "", data))
        # APEv2 items are stored sorted by size, so present the front cover first.
        return TagSnapshot(f, self._custom_current(active), ordered_pictures(pics), self.tag_format)

    def _set(self, key: str, value: str):
        if key in self.tags:
            del self.tags[key]
        if value != "":
            self.tags[key] = value

    def apply(self, changes: TagChanges) -> list:
        warnings = []
        active = self._active()
        if changes.fields:
            merged = self.merged_fields(changes)
            for field, value in changes.fields.items():
                if field not in FIELD_KEYS or field in ("track", "tracktotal", "disc", "disctotal"):
                    continue
                value = "" if value is None else str(value)
                if field == "compilation":
                    value = "1" if truthy(value) else ""
                self._set(active[field], value)
            for field in ("track", "disc"):
                if field in changes.fields or field + "total" in changes.fields:
                    n, tot = clean_number(merged[field]), clean_number(merged[field + "total"])
                    self._set(active[field], ("%s/%s" % (n or "0", tot)) if tot else n)

        if changes.custom is not None:
            current = self._custom_current(active)
            used = {k.lower() for k in active.values()}
            to_set, to_delete = custom_diff(current, changes.custom, normalize=str.lower)
            for key in to_delete:
                self._set(key, "")
            for key, value in to_set.items():
                if key.lower() in used or _is_cover_key(key) or not (2 <= len(key) <= 255):
                    raise TagError("Invalid field name: %s" % key, "invalid-custom-key", key)
                self._set(key, value)

        if changes.pictures is not None:
            for key in [k for k in self.tags.keys() if _is_cover_key(k)]:
                del self.tags[key]
            used_keys = set()
            for p in ordered_pictures(changes.pictures):
                key = COVER_KEYS.get(int(p.type), COVER_KEYS[0])
                if key in used_keys:
                    key = COVER_KEYS[0]
                if key in used_keys:
                    warnings.append("ape-duplicate-picture-type")
                    continue
                used_keys.add(key)
                ext = "png" if p.mime == images.PNG else "jpg"
                name = "cover.%s" % ext
                self.tags[key] = APEValue(name.encode("utf-8") + b"\x00" + p.data, BINARY)
        return warnings

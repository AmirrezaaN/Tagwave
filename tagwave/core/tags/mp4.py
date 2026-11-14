"""iTunes-style MP4 atoms (M4A / M4B / MP4: AAC and ALAC)."""

from __future__ import annotations

from mutagen._constants import GENRES
from mutagen.mp4 import AtomDataType, MP4Cover, MP4FreeForm

from .. import images
from .base import (FIELD_KEYS, Picture, TagChanges, TagError, TagHandler, TagSnapshot,
                   clean_number, custom_diff, empty_fields, join_values, ordered_pictures,
                   truthy)

FF = "----:com.apple.iTunes:"

KEYS = {
    "title": ["\xa9nam"], "artist": ["\xa9ART"], "album": ["\xa9alb"], "albumartist": ["aART"],
    "date": ["\xa9day"], "genre": ["\xa9gen"], "composer": ["\xa9wrt"],
    "lyricist": [FF + "LYRICIST"], "conductor": [FF + "CONDUCTOR"], "comment": ["\xa9cmt"],
    "lyrics": ["\xa9lyr"], "bpm": ["tmpo"],
    "publisher": [FF + "LABEL", "\xa9pub", FF + "PUBLISHER"],
    "copyright": ["cprt"], "encodedby": ["\xa9enc", "\xa9too"], "isrc": [FF + "ISRC"],
    "grouping": ["\xa9grp"], "compilation": ["cpil"],
}
# Internal iTunes data that should never be shown or touched.
HIDDEN_FREEFORM = {"iTunSMPB", "iTunNORM", "Encoding Params", "iTunes_CDDB_IDs", "iTunMOVI"}


def _decode_freeform(v) -> str | None:
    if isinstance(v, MP4FreeForm):
        if v.dataformat == AtomDataType.UTF16:
            return bytes(v).decode("utf-16-be", "replace")
        if v.dataformat in (AtomDataType.UTF8, AtomDataType.IMPLICIT):
            return bytes(v).decode("utf-8", "replace")
        return None
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", "replace")
    return str(v)


def _custom_name(key: str) -> str:
    return key[len(FF):] if key.startswith(FF) else key


def _custom_key(name: str) -> str:
    return name if name.startswith("----:") else FF + name


class MP4Handler(TagHandler):
    tag_format = "iTunes MP4"
    picture_types = False
    picture_desc = False

    def __init__(self, audio):
        super().__init__(audio)
        if audio.tags is None:
            audio.add_tags()
        self.tags = audio.tags

    def _active(self) -> dict:
        return {f: next((c for c in cands if c in self.tags), cands[0]) for f, cands in KEYS.items()}

    def _text(self, key: str) -> str:
        vals = self.tags.get(key)
        if not vals:
            return ""
        if key.startswith("----:"):
            return join_values(x for x in (_decode_freeform(v) for v in vals) if x is not None)
        return join_values(vals)

    def _custom_current(self, active: dict) -> list:
        used = set(active.values())
        out = []
        for key in self.tags.keys():
            if not key.startswith("----:") or key in used:
                continue
            name = _custom_name(key)
            if name in HIDDEN_FREEFORM:
                continue
            decoded = [_decode_freeform(v) for v in self.tags[key]]
            if any(d is None for d in decoded):
                continue  # binary data: leave alone
            out.append([name, join_values(decoded)])
        return out

    def read(self) -> TagSnapshot:
        t = self.tags
        active = self._active()
        f = empty_fields()
        for field, key in active.items():
            if field in ("bpm", "compilation"):
                continue
            if field in ("lyrics", "comment"):
                vals = t.get(key) or []
                f[field] = "\n".join(str(v) for v in vals)
            else:
                f[field] = self._text(key)
        if not f["genre"] and t.get("gnre"):
            idx = t["gnre"][0] - 1
            if 0 <= idx < len(GENRES):
                f["genre"] = GENRES[idx]
        if t.get("tmpo"):
            f["bpm"] = str(t["tmpo"][0])
        if t.get("cpil"):
            f["compilation"] = "1" if t["cpil"] else ""
        if t.get("trkn"):
            n, tot = (list(t["trkn"][0]) + [0, 0])[:2]
            f["track"] = str(n) if n else ""
            f["tracktotal"] = str(tot) if tot else ""
        if t.get("disk"):
            n, tot = (list(t["disk"][0]) + [0, 0])[:2]
            f["disc"] = str(n) if n else ""
            f["disctotal"] = str(tot) if tot else ""

        pics = []
        for i, cov in enumerate(t.get("covr") or []):
            data = bytes(cov)
            mime = images.sniff_mime(data) or (
                "image/png" if getattr(cov, "imageformat", None) == MP4Cover.FORMAT_PNG else "image/jpeg")
            pics.append(Picture(3 if i == 0 else 0, mime, "", data))
        return TagSnapshot(f, self._custom_current(active), pics, self.tag_format)

    def _del(self, key):
        if key in self.tags:
            del self.tags[key]

    def apply(self, changes: TagChanges) -> list:
        t = self.tags
        active = self._active()
        if changes.fields:
            merged = self.merged_fields(changes)
            for field, value in changes.fields.items():
                if field not in FIELD_KEYS or field in ("track", "tracktotal", "disc", "disctotal"):
                    continue
                value = "" if value is None else str(value)
                key = active[field]
                self._del(key)
                if field == "genre":
                    self._del("gnre")
                if value == "":
                    continue
                if field == "bpm":
                    try:
                        t["tmpo"] = [int(round(float(value)))]
                    except ValueError:
                        raise TagError("BPM must be a number.", "invalid-bpm", "bpm") from None
                elif field == "compilation":
                    if truthy(value):
                        t["cpil"] = True
                elif key.startswith("----:"):
                    t[key] = [MP4FreeForm(value.encode("utf-8"), AtomDataType.UTF8)]
                else:
                    t[key] = [value]
            for field, atom in (("track", "trkn"), ("disc", "disk")):
                if field in changes.fields or field + "total" in changes.fields:
                    n = clean_number(merged[field])
                    tot = clean_number(merged[field + "total"])
                    self._del(atom)
                    if n or tot:
                        t[atom] = [(int(n or 0), int(tot or 0))]

        if changes.custom is not None:
            current = self._custom_current(active)
            used = {_custom_name(k) for k in active.values()}
            to_set, to_delete = custom_diff(current, changes.custom)
            for name in to_delete:
                self._del(_custom_key(name))
            for name, value in to_set.items():
                if name in used or name in HIDDEN_FREEFORM:
                    raise TagError("'%s' is already a standard field." % name, "custom-key-reserved", name)
                t[_custom_key(name)] = [MP4FreeForm(value.encode("utf-8"), AtomDataType.UTF8)]

        if changes.pictures is not None:
            self._del("covr")
            covers = []
            for p in ordered_pictures(changes.pictures):
                fmt = MP4Cover.FORMAT_PNG if p.mime == images.PNG else MP4Cover.FORMAT_JPEG
                covers.append(MP4Cover(p.data, imageformat=fmt))
            if covers:
                t["covr"] = covers
        return []

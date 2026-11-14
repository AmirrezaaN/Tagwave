"""ASF / Windows Media Audio attributes."""

from __future__ import annotations

import struct

from mutagen.asf import (ASFBoolAttribute, ASFByteArrayAttribute, ASFDWordAttribute,
                         ASFUnicodeAttribute)

from .. import images
from .base import (FIELD_KEYS, Picture, TagChanges, TagError, TagHandler, TagSnapshot,
                   clean_number, custom_diff, empty_fields, join_values, ordered_pictures,
                   split_pair, truthy)

KEYS = {
    "title": ["Title"], "artist": ["Author"], "album": ["WM/AlbumTitle"],
    "albumartist": ["WM/AlbumArtist"], "date": ["WM/Year"], "genre": ["WM/Genre"],
    "track": ["WM/TrackNumber"], "tracktotal": ["TotalTracks", "WM/TrackTotal"],
    "disc": ["WM/PartOfSet"], "composer": ["WM/Composer"], "lyricist": ["WM/Writer"],
    "conductor": ["WM/Conductor"], "comment": ["Description"], "lyrics": ["WM/Lyrics"],
    "bpm": ["WM/BeatsPerMinute"], "publisher": ["WM/Publisher"], "copyright": ["Copyright"],
    "encodedby": ["WM/EncodedBy"], "isrc": ["WM/ISRC"],
    "grouping": ["WM/ContentGroupDescription"], "compilation": ["WM/IsCompilation"],
}
PICTURE_KEY = "WM/Picture"
# Technical attributes written by encoders - never shown as custom fields.
HIDDEN = {"WM/MediaClassPrimaryID", "WM/MediaClassSecondaryID", "WM/Provider",
          "WM/ProviderRating", "WM/ProviderStyle", "WMFSDKVersion", "WMFSDKNeeded",
          "IsVBR", "WM/EncodingTime", "MediaFoundationVersion", "WM/WMContentID",
          "WM/WMCollectionID", "WM/WMCollectionGroupID", "WM/UniqueFileIdentifier",
          "WM/Track", "WM/MCDI", "DeviceConformanceTemplate", "WM/ToolName",
          "WM/ToolVersion", "Rating"}


def parse_wm_picture(raw: bytes) -> Picture | None:
    try:
        ptype = raw[0]
        size = struct.unpack_from("<I", raw, 1)[0]
        pos = 5

        def read_wstr(p):
            end = p
            while end + 1 < len(raw) and raw[end:end + 2] != b"\x00\x00":
                end += 2
            return raw[p:end].decode("utf-16-le", "replace"), end + 2

        mime, pos = read_wstr(pos)
        desc, pos = read_wstr(pos)
        data = raw[pos:pos + size]
        if not data:
            return None
        return Picture(int(ptype), images.sniff_mime(data) or mime or "image/jpeg", desc, data)
    except Exception:
        return None


def build_wm_picture(p: Picture) -> bytes:
    return (struct.pack("<BI", int(p.type) & 0xFF, len(p.data))
            + p.mime.encode("utf-16-le") + b"\x00\x00"
            + (p.desc or "").encode("utf-16-le") + b"\x00\x00"
            + p.data)


class ASFHandler(TagHandler):
    tag_format = "ASF (WMA)"

    def __init__(self, audio):
        super().__init__(audio)
        if audio.tags is None:
            audio.add_tags()
        self.tags = audio.tags

    def _active(self) -> dict:
        return {f: next((c for c in cands if c in self.tags), cands[0]) for f, cands in KEYS.items()}

    def _vals(self, key) -> list:
        return [a.value for a in self.tags.get(key, [])]

    def _custom_current(self, active) -> list:
        used = set(active.values())
        out = []
        for key in self.tags.keys():
            if key in used or key in HIDDEN or key == PICTURE_KEY:
                continue
            attrs = self.tags[key]
            if not all(isinstance(a, ASFUnicodeAttribute) for a in attrs):
                continue
            out.append([key, join_values(a.value for a in attrs)])
        return out

    def read(self) -> TagSnapshot:
        active = self._active()
        f = empty_fields()
        for field, key in active.items():
            vals = self._vals(key)
            if vals:
                f[field] = join_values(vals)
        if not f["track"] and self._vals("WM/Track"):
            try:
                f["track"] = str(int(self._vals("WM/Track")[0]) + 1)
            except (TypeError, ValueError):
                pass
        if "/" in f["track"]:
            f["track"], tot = split_pair(f["track"])
            f["tracktotal"] = f["tracktotal"] or tot
        if f["disc"]:
            f["disc"], f["disctotal"] = split_pair(f["disc"])
        f["compilation"] = "1" if truthy(f["compilation"]) else ""
        pics = []
        for a in self.tags.get(PICTURE_KEY, []):
            p = parse_wm_picture(bytes(a.value))
            if p:
                pics.append(p)
        # ASF stores large attributes in a different header object, so file order
        # isn't stable: always present the front cover first.
        return TagSnapshot(f, self._custom_current(active), ordered_pictures(pics), self.tag_format)

    def _del(self, key):
        if key in self.tags:
            del self.tags[key]

    def _set(self, key: str, value: str, prefer_dword: bool = False):
        old = self.tags.get(key, [])
        was_dword = bool(old) and isinstance(old[0], ASFDWordAttribute)
        self._del(key)
        if value == "":
            return
        if (was_dword or prefer_dword) and value.isdigit():
            self.tags[key] = [ASFDWordAttribute(int(value))]
        else:
            self.tags[key] = [ASFUnicodeAttribute(value)]

    def apply(self, changes: TagChanges) -> list:
        active = self._active()
        if changes.fields:
            merged = self.merged_fields(changes)
            for field, value in changes.fields.items():
                if field not in FIELD_KEYS or field in ("track", "tracktotal", "disc", "disctotal"):
                    continue
                value = "" if value is None else str(value)
                key = active[field]
                if field == "compilation":
                    self._del(key)
                    if truthy(value):
                        self.tags[key] = [ASFBoolAttribute(True)]
                else:
                    self._set(key, value)
            if "track" in changes.fields or "tracktotal" in changes.fields:
                self._set(active["track"], clean_number(merged["track"]))
                self._set(active["tracktotal"], clean_number(merged["tracktotal"]))
                self._del("WM/Track")
            if "disc" in changes.fields or "disctotal" in changes.fields:
                n, tot = clean_number(merged["disc"]), clean_number(merged["disctotal"])
                self._set(active["disc"], ("%s/%s" % (n or "0", tot)) if tot else n)

        if changes.custom is not None:
            current = self._custom_current(active)
            used = set(active.values()) | HIDDEN | {PICTURE_KEY}
            to_set, to_delete = custom_diff(current, changes.custom)
            for key in to_delete:
                self._del(key)
            for key, value in to_set.items():
                if key in used:
                    raise TagError("'%s' is already a standard field." % key, "custom-key-reserved", key)
                self._set(key, value)

        if changes.pictures is not None:
            self._del(PICTURE_KEY)
            attrs = [ASFByteArrayAttribute(build_wm_picture(p)) for p in ordered_pictures(changes.pictures)]
            if attrs:
                self.tags[PICTURE_KEY] = attrs
        return []

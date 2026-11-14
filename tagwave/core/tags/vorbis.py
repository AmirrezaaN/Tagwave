"""Vorbis comments (FLAC, Ogg Vorbis, Opus, Ogg FLAC, Speex)."""

from __future__ import annotations

import base64

from mutagen._vorbis import is_valid_key
from mutagen.flac import FLAC
from mutagen.flac import Picture as FlacPicture

from .. import images
from .base import (FIELD_KEYS, Picture, TagChanges, TagError, TagHandler, TagSnapshot,
                   clean_number, custom_diff, empty_fields, join_values, ordered_pictures,
                   split_pair, truthy)

# field -> candidate keys (first is the default used for new tags)
KEYS = {
    "title": ["TITLE"], "artist": ["ARTIST"], "album": ["ALBUM"],
    "albumartist": ["ALBUMARTIST", "ALBUM ARTIST", "ALBUM_ARTIST"],
    "date": ["DATE", "YEAR"], "genre": ["GENRE"],
    "track": ["TRACKNUMBER"], "tracktotal": ["TRACKTOTAL", "TOTALTRACKS"],
    "disc": ["DISCNUMBER"], "disctotal": ["DISCTOTAL", "TOTALDISCS"],
    "composer": ["COMPOSER"], "lyricist": ["LYRICIST"], "conductor": ["CONDUCTOR"],
    "comment": ["COMMENT", "DESCRIPTION"], "lyrics": ["LYRICS", "UNSYNCEDLYRICS"],
    "bpm": ["BPM"], "publisher": ["PUBLISHER", "LABEL", "ORGANIZATION"],
    "copyright": ["COPYRIGHT"], "encodedby": ["ENCODEDBY", "ENCODED-BY"],
    "isrc": ["ISRC"], "grouping": ["GROUPING", "CONTENTGROUP"],
    "compilation": ["COMPILATION"],
}
PICTURE_KEYS = {"METADATA_BLOCK_PICTURE", "COVERART", "COVERARTMIME"}


class VorbisHandler(TagHandler):
    tag_format = "Vorbis Comment"

    def __init__(self, audio):
        super().__init__(audio)
        if audio.tags is None:
            audio.add_tags()
        self.tags = audio.tags
        self.is_flac = isinstance(audio, FLAC)

    # ------------------------------------------------------------- helpers
    def _values(self) -> dict:
        """UPPERCASE key -> [values] preserving first-seen order."""
        out: dict = {}
        for k, v in self.tags:
            out.setdefault(k.upper(), []).append(v)
        return out

    def _active_keys(self, values: dict) -> dict:
        """field -> the key actually used in this file (or the default)."""
        active = {}
        for field, cands in KEYS.items():
            active[field] = next((c for c in cands if values.get(c)), cands[0])
        return active

    def _set(self, key: str, value: str):
        if key.lower() in self.tags:
            del self.tags[key]
        if value != "":
            self.tags[key] = [value]

    # ---------------------------------------------------------------- read
    def read(self) -> TagSnapshot:
        values = self._values()
        active = self._active_keys(values)
        f = empty_fields()
        for field, key in active.items():
            vals = values.get(key)
            if vals:
                f[field] = "\n".join(vals) if field in ("lyrics", "comment") else join_values(vals)
        if f["track"] and "/" in f["track"]:
            num, tot = split_pair(f["track"])
            f["track"] = num
            f["tracktotal"] = f["tracktotal"] or tot
        if f["disc"] and "/" in f["disc"]:
            num, tot = split_pair(f["disc"])
            f["disc"] = num
            f["disctotal"] = f["disctotal"] or tot
        f["compilation"] = "1" if truthy(f["compilation"]) else ""

        used = set(active.values())
        custom = [[k, join_values(v)] for k, v in values.items()
                  if k not in used and k not in PICTURE_KEYS]

        pics = []
        if self.is_flac:
            for p in self.audio.pictures:
                pics.append(Picture(int(p.type), images.sniff_mime(p.data) or p.mime,
                                    p.desc or "", bytes(p.data)))
        for b64 in values.get("METADATA_BLOCK_PICTURE", []):
            try:
                p = FlacPicture(base64.b64decode(b64))
            except Exception:
                continue
            pics.append(Picture(int(p.type), images.sniff_mime(p.data) or p.mime,
                                p.desc or "", bytes(p.data)))
        for b64 in values.get("COVERART", []):
            try:
                data = base64.b64decode(b64)
            except Exception:
                continue
            pics.append(Picture(3, images.sniff_mime(data) or "image/jpeg", "", data))
        return TagSnapshot(f, custom, pics, self.tag_format)

    # --------------------------------------------------------------- write
    def apply(self, changes: TagChanges) -> list:
        values = self._values()
        active = self._active_keys(values)
        if changes.fields:
            merged = self.merged_fields(changes)
            for field, value in changes.fields.items():
                if field not in FIELD_KEYS or field in ("track", "tracktotal", "disc", "disctotal"):
                    continue
                value = "" if value is None else str(value)
                if field == "compilation":
                    value = "1" if truthy(value) else ""
                self._set(active[field], value)
            if any(k in changes.fields for k in ("track", "tracktotal")):
                self._set(active["track"], clean_number(merged["track"]))
                self._set(active["tracktotal"], clean_number(merged["tracktotal"]))
            if any(k in changes.fields for k in ("disc", "disctotal")):
                self._set(active["disc"], clean_number(merged["disc"]))
                self._set(active["disctotal"], clean_number(merged["disctotal"]))

        if changes.custom is not None:
            used = set(active.values())
            current = [[k, join_values(v)] for k, v in values.items()
                       if k not in used and k not in PICTURE_KEYS]
            to_set, to_delete = custom_diff(current, changes.custom, normalize=str.upper)
            for key in to_delete:
                self._set(key, "")
            for key, value in to_set.items():
                key = key.upper()
                if not is_valid_key(key) or key in PICTURE_KEYS:
                    raise TagError("Invalid field name: %s" % key, "invalid-custom-key", key)
                if key in used:
                    raise TagError("'%s' is already a standard field." % key, "custom-key-reserved", key)
                self._set(key, value)

        if changes.pictures is not None:
            for key in PICTURE_KEYS:
                self._set(key, "")
            pics = ordered_pictures(changes.pictures)
            if self.is_flac:
                self.audio.clear_pictures()
                for p in pics:
                    self.audio.add_picture(self._flac_picture(p))
            else:
                encoded = [base64.b64encode(self._flac_picture(p).write()).decode("ascii") for p in pics]
                if encoded:
                    self.tags["METADATA_BLOCK_PICTURE"] = encoded
        return []

    @staticmethod
    def _flac_picture(p: Picture) -> FlacPicture:
        meta = images.image_meta(p.data)
        pic = FlacPicture()
        pic.type = int(p.type)
        pic.mime = p.mime
        pic.desc = p.desc or ""
        pic.width = meta.width
        pic.height = meta.height
        pic.depth = meta.depth
        pic.colors = meta.colors
        pic.data = p.data
        return pic

    def save(self, filename, opts) -> None:
        self.audio.save(filename)

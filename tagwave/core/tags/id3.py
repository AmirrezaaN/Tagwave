"""ID3v2 (MP3, WAV, AIFF, DSF, TTA)."""

from __future__ import annotations

import re

from mutagen.id3 import (APIC, COMM, SYLT, TCMP, TCON, TDRC, TPOS, TRCK, TXXX, USLT,
                         Frames)
from mutagen.mp3 import MP3
from mutagen.trueaudio import TrueAudio
from mutagen.wave import WAVE

from .. import images, lyrics
from .base import (FIELD_KEYS, Picture, SaveOptions, TagChanges, TagError, TagHandler,
                   TagSnapshot, clean_number, custom_diff, empty_fields, join_values,
                   ordered_pictures, split_pair, truthy)

TEXT_FRAMES = {
    "title": "TIT2", "artist": "TPE1", "album": "TALB", "albumartist": "TPE2",
    "composer": "TCOM", "lyricist": "TEXT", "conductor": "TPE3", "bpm": "TBPM",
    "publisher": "TPUB", "copyright": "TCOP", "encodedby": "TENC", "isrc": "TSRC",
    "grouping": "TIT1",
}

_DATE_OK = re.compile(r"^\d{4}(-\d{2}(-\d{2}([T ]\d{2}(:\d{2}(:\d{2})?)?)?)?)?$")


def _first(frames, desc=""):
    for f in frames:
        if getattr(f, "desc", "") == desc:
            return f
    return None


class ID3Handler(TagHandler):
    def __init__(self, audio):
        super().__init__(audio)
        self.had_tags = audio.tags is not None
        if audio.tags is None:
            audio.add_tags()
        self.tags = audio.tags
        self.orig_version = self.tags.version if self.had_tags else None

    @property
    def tag_format(self) -> str:
        v = self.orig_version
        if v and v[0] == 2 and v[1] in (2, 3, 4):
            return "ID3v2.%d" % v[1]
        return "ID3v2.3"

    # ------------------------------------------------------------------ read
    def read(self) -> TagSnapshot:
        t = self.tags
        f = empty_fields()
        for key, fid in TEXT_FRAMES.items():
            fr = t.get(fid)
            if fr is not None:
                f[key] = join_values(fr.text)
        fr = t.get("TCON")
        if fr is not None:
            f["genre"] = join_values(fr.genres)
        fr = t.get("TDRC")
        if fr is not None:
            f["date"] = join_values(x.text if hasattr(x, "text") else x for x in fr.text)
        fr = t.get("TCMP")
        if fr is not None and fr.text and truthy(str(fr.text[0])):
            f["compilation"] = "1"
        fr = t.get("TRCK")
        if fr is not None and fr.text:
            f["track"], f["tracktotal"] = split_pair(str(fr.text[0]))
        fr = t.get("TPOS")
        if fr is not None and fr.text:
            f["disc"], f["disctotal"] = split_pair(str(fr.text[0]))
        comm = _first(t.getall("COMM"))
        if comm is not None:
            f["comment"] = "\n".join(str(x) for x in comm.text)
        uslt = _first(t.getall("USLT"))
        if uslt is not None:
            f["lyrics"] = uslt.text
        else:
            sylt = _first(t.getall("SYLT"))
            if sylt is not None:
                f["lyrics"] = self._sylt_to_lrc(sylt)

        custom = []
        for fr in t.getall("TXXX"):
            custom.append([fr.desc, join_values(fr.text)])

        pics = []
        for fr in t.getall("APIC"):
            if fr.mime == "-->":
                continue  # linked image, not embedded data
            mime = images.sniff_mime(fr.data) or fr.mime or "image/jpeg"
            pics.append(Picture(int(fr.type), mime, fr.desc or "", bytes(fr.data)))
        return TagSnapshot(f, custom, pics, self.tag_format)

    @staticmethod
    def _sylt_to_lrc(sylt) -> str:
        entries = []
        for item in sylt.text:
            text, stamp = item
            ms = stamp if sylt.format == 2 else 0
            entries.append((int(ms), text.strip()))
        return lyrics.format_lrc(entries)

    # ----------------------------------------------------------------- write
    def apply(self, changes: TagChanges) -> list:
        warnings: list = []
        t = self.tags
        if changes.fields:
            merged = self.merged_fields(changes)
            for key, value in changes.fields.items():
                if key not in FIELD_KEYS:
                    continue
                value = "" if value is None else str(value)
                if key in TEXT_FRAMES:
                    fid = TEXT_FRAMES[key]
                    t.delall(fid)
                    if value:
                        t.add(Frames[fid](encoding=3, text=[value]))
                elif key == "genre":
                    t.delall("TCON")
                    if value:
                        t.add(TCON(encoding=3, text=[value]))
                elif key == "date":
                    t.delall("TDRC")
                    if value:
                        if not _DATE_OK.match(value.strip()):
                            raise TagError("Year must look like 2024 or 2024-05-31.")
                        t.add(TDRC(encoding=3, text=[value.strip()]))
                elif key == "compilation":
                    t.delall("TCMP")
                    if truthy(value):
                        t.add(TCMP(encoding=3, text=["1"]))
                elif key == "comment":
                    lang = "eng"
                    for fr in list(t.getall("COMM")):
                        if fr.desc == "":
                            lang = fr.lang or lang
                            t.delall(fr.HashKey)
                    if value:
                        t.add(COMM(encoding=3, lang=lang, desc="", text=[value]))
                elif key == "lyrics":
                    self._write_lyrics(value)
            if any(k in changes.fields for k in ("track", "tracktotal")):
                self._write_pair("TRCK", TRCK, merged["track"], merged["tracktotal"])
            if any(k in changes.fields for k in ("disc", "disctotal")):
                self._write_pair("TPOS", TPOS, merged["disc"], merged["disctotal"])

        if changes.custom is not None:
            current = [[fr.desc, join_values(fr.text)] for fr in t.getall("TXXX")]
            to_set, to_delete = custom_diff(current, changes.custom)
            for desc in to_delete:
                t.delall("TXXX:" + desc)
            for desc, value in to_set.items():
                t.delall("TXXX:" + desc)
                t.add(TXXX(encoding=3, desc=desc, text=[value]))

        if changes.pictures is not None:
            t.delall("APIC")
            used = set()
            for p in ordered_pictures(changes.pictures):
                desc = p.desc or ""
                base, n = desc, 2
                while desc in used:
                    desc = "%s (%d)" % (base, n) if base else "(%d)" % n
                    n += 1
                used.add(desc)
                t.add(APIC(encoding=3, mime=p.mime, type=int(p.type), desc=desc, data=p.data))
        return warnings

    def _write_pair(self, fid, cls, num, total):
        self.tags.delall(fid)
        num, total = clean_number(num), clean_number(total)
        if not num and not total:
            return
        text = "%s/%s" % (num or "0", total) if total else num
        self.tags.add(cls(encoding=3, text=[text]))

    def _write_lyrics(self, value: str):
        t = self.tags
        lang = "eng"
        for fr in list(t.getall("USLT")):
            if fr.desc == "":
                lang = fr.lang or lang
                t.delall(fr.HashKey)
        for fr in list(t.getall("SYLT")):
            if fr.desc == "":
                t.delall(fr.HashKey)
        if not value:
            return
        t.add(USLT(encoding=3, lang=lang, desc="", text=value))
        entries, _ = lyrics.parse_lrc(value)
        if entries:
            t.add(SYLT(encoding=3, lang=lang, format=2, type=1, desc="",
                       text=[(line, ms) for ms, line in entries]))

    def save(self, filename: str, opts: SaveOptions) -> None:
        if opts.id3_version == "3":
            version = 3
        elif opts.id3_version == "4":
            version = 4
        else:
            v = self.orig_version
            version = 4 if (v and v[1] >= 4) else 3
        if version == 3:
            self.tags.update_to_v23()
        if isinstance(self.audio, (MP3, TrueAudio, WAVE)):
            v1 = {"keep": 1, "remove": 0, "write": 2}.get(opts.id3v1, 1)
            self.audio.save(filename, v1=v1, v2_version=version)
        else:
            # AIFF / DSF containers have no ID3v1 option.
            self.audio.save(filename, v2_version=version)

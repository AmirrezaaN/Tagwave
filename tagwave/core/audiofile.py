"""Open audio files, describe their technical properties, and save tags safely."""

from __future__ import annotations

import os
import secrets
import shutil
import struct
from dataclasses import dataclass

import mutagen
from mutagen.aac import AAC
from mutagen.aiff import AIFF
from mutagen.asf import ASF
from mutagen.dsf import DSF
from mutagen.flac import FLAC
from mutagen.monkeysaudio import MonkeysAudio
from mutagen.mp3 import MP3, BitrateMode
from mutagen.mp4 import MP4
from mutagen.musepack import Musepack
from mutagen.oggflac import OggFLAC
from mutagen.oggopus import OggOpus
from mutagen.oggspeex import OggSpeex
from mutagen.oggvorbis import OggVorbis
from mutagen.optimfrog import OptimFROG
from mutagen.trueaudio import TrueAudio
from mutagen.wave import WAVE
from mutagen.wavpack import WavPack

from . import ffmpeg, winfs
from .errors import (CannotTagError, FileChangedError, FileReadOnlyError, IntegrityError,
                     UnsupportedFileError)
from .tags import SaveOptions, TagChanges, TagSnapshot, empty_fields, handler_for, validate_fields

SUPPORTED_EXTENSIONS = (
    ".mp3", ".flac", ".m4a", ".m4b", ".mp4", ".aac", ".ogg", ".oga", ".opus", ".spx",
    ".wav", ".aif", ".aiff", ".aifc", ".wma", ".asf", ".ape", ".wv", ".mpc", ".tta",
    ".ofr", ".dsf",
)

_KINDS = [MP3, FLAC, MP4, OggVorbis, OggOpus, OggFLAC, OggSpeex, WAVE, AIFF, ASF,
          MonkeysAudio, WavPack, Musepack, TrueAudio, OptimFROG, DSF, AAC]


def is_supported_path(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS


def open_audio(path: str):
    try:
        audio = mutagen.File(path, options=_KINDS)
    except mutagen.MutagenError as exc:
        raise UnsupportedFileError("The file could not be read: %s" % exc) from exc
    if audio is None:
        raise UnsupportedFileError("This is not a supported audio file.")
    return audio


# ---------------------------------------------------------------- tech info

def _wav_format_tag(path: str) -> int | None:
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:4] not in (b"RIFF", b"RF64") or head[8:12] != b"WAVE":
                return None
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    return None
                cid, size = hdr[:4], struct.unpack("<I", hdr[4:])[0]
                if cid == b"fmt ":
                    data = f.read(min(size, 40))
                    tag = struct.unpack("<H", data[:2])[0]
                    if tag == 0xFFFE and len(data) >= 26:
                        tag = struct.unpack("<H", data[24:26])[0]
                    return tag
                f.seek(size + (size & 1), 1)
    except OSError:
        return None


def _aifc_compression(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            head = f.read(12)
            if head[:4] != b"FORM" or head[8:12] != b"AIFC":
                return None
            while True:
                hdr = f.read(8)
                if len(hdr) < 8:
                    return None
                cid, size = hdr[:4], struct.unpack(">I", hdr[4:])[0]
                if cid == b"COMM":
                    data = f.read(min(size, 22))
                    return data[18:22] if len(data) >= 22 else None
                f.seek(size + (size & 1), 1)
    except OSError:
        return None


def _wavpack_hybrid(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(32)
        return head[:4] == b"wvpk" and bool(struct.unpack("<I", head[24:28])[0] & 0x8)
    except (OSError, struct.error):
        return False


def describe(audio, path: str, size: int) -> dict:
    info = audio.info
    d = {
        "container": "", "codec": "", "codecDetail": "", "lossless": False,
        "duration": float(getattr(info, "length", 0) or 0),
        "bitrate": int(getattr(info, "bitrate", 0) or 0),
        "sampleRate": int(getattr(info, "sample_rate", 0) or 0),
        "bitsPerSample": int(getattr(info, "bits_per_sample", 0) or 0) or None,
        "channels": int(getattr(info, "channels", 0) or 0),
        "bitrateMode": None, "encoder": None,
    }
    if isinstance(audio, MP3):
        d.update(container="MP3", codec="MP3")
        mode = getattr(info, "bitrate_mode", BitrateMode.UNKNOWN)
        d["bitrateMode"] = {BitrateMode.CBR: "CBR", BitrateMode.VBR: "VBR",
                            BitrateMode.ABR: "ABR"}.get(mode)
        d["encoder"] = getattr(info, "encoder_info", "") or None
        d["bitsPerSample"] = None
    elif isinstance(audio, FLAC):
        d.update(container="FLAC", codec="FLAC", lossless=True)
    elif isinstance(audio, MP4):
        codec = (getattr(info, "codec", "") or "").lower()
        if codec == "alac":
            d.update(container="MP4", codec="ALAC", lossless=True)
        elif codec.startswith("mp4a.40") or codec == "mp4a":
            d.update(container="MP4", codec="AAC", bitsPerSample=None)
        elif codec in ("mp4a.69", "mp4a.6b"):
            d.update(container="MP4", codec="MP3", bitsPerSample=None)
        else:
            d.update(container="MP4", codec=codec.upper() or "Unknown", bitsPerSample=None)
        d["codecDetail"] = getattr(info, "codec_description", "") or ""
    elif isinstance(audio, OggVorbis):
        d.update(container="Ogg", codec="Vorbis", bitsPerSample=None)
    elif isinstance(audio, OggOpus):
        d.update(container="Ogg", codec="Opus", bitsPerSample=None, sampleRate=48000)
    elif isinstance(audio, OggFLAC):
        d.update(container="Ogg", codec="FLAC", lossless=True)
    elif isinstance(audio, OggSpeex):
        d.update(container="Ogg", codec="Speex", bitsPerSample=None)
    elif isinstance(audio, WAVE):
        tag = _wav_format_tag(path)
        if tag == 1:
            d.update(container="WAV", codec="PCM", lossless=True)
        elif tag == 3:
            d.update(container="WAV", codec="PCM (float)", lossless=True)
        else:
            d.update(container="WAV", codec="Compressed (0x%04X)" % (tag or 0))
    elif isinstance(audio, AIFF):
        comp = _aifc_compression(path)
        if comp in (None, b"NONE", b"sowt", b"twos", b"in24", b"in32", b"raw "):
            d.update(container="AIFF", codec="PCM", lossless=True)
        elif comp in (b"fl32", b"FL32", b"fl64", b"FL64"):
            d.update(container="AIFF", codec="PCM (float)", lossless=True)
        else:
            d.update(container="AIFF", codec=comp.decode("latin-1").strip() or "Compressed")
    elif isinstance(audio, ASF):
        name = getattr(info, "codec_name", "") or "WMA"
        lossless = "lossless" in name.lower()
        d.update(container="ASF", codec="WMA Lossless" if lossless else "WMA", lossless=lossless,
                 codecDetail=name)
        if not lossless:
            d["bitsPerSample"] = None
    elif isinstance(audio, MonkeysAudio):
        d.update(container="APE", codec="Monkey's Audio", lossless=True)
    elif isinstance(audio, WavPack):
        hybrid = _wavpack_hybrid(path)
        d.update(container="WavPack", codec="WavPack (hybrid)" if hybrid else "WavPack",
                 lossless=not hybrid)
    elif isinstance(audio, Musepack):
        d.update(container="Musepack", codec="Musepack", bitsPerSample=None)
    elif isinstance(audio, TrueAudio):
        d.update(container="TTA", codec="TTA", lossless=True)
    elif isinstance(audio, OptimFROG):
        d.update(container="OptimFROG", codec="OptimFROG", lossless=True)
    elif isinstance(audio, DSF):
        d.update(container="DSF", codec="DSD", lossless=True, bitsPerSample=1)
    elif isinstance(audio, AAC):
        d.update(container="AAC (ADTS)", codec="AAC", bitsPerSample=None)
    if not d["bitrate"] and d["duration"] > 0:
        d["bitrate"] = int(size * 8 / d["duration"])
    return d


# ------------------------------------------------------------------ loading

@dataclass
class LoadedFile:
    path: str
    size: int
    mtime_ns: int
    info: dict
    snapshot: TagSnapshot
    can_tag: bool
    picture_types: bool
    picture_desc: bool

    @property
    def stamp(self) -> tuple[int, int]:
        return (self.size, self.mtime_ns)


def load(path: str) -> LoadedFile:
    path = os.path.abspath(path)
    st = os.stat(path)
    audio = open_audio(path)
    info = describe(audio, path, st.st_size)
    handler = handler_for(audio)
    if handler is None:
        snap = TagSnapshot(empty_fields(), [], [], "")
        return LoadedFile(path, st.st_size, st.st_mtime_ns, info, snap, False, False, False)
    snap = handler.read()
    return LoadedFile(path, st.st_size, st.st_mtime_ns, info, snap, True,
                      handler.picture_types, handler.picture_desc)


# ------------------------------------------------------------------- saving

def _temp_name(path: str) -> str:
    d, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    return os.path.join(d, ".%s.tagwave-%s%s" % (stem[:80], secrets.token_hex(4), ext))


def write_tags(path: str, changes: TagChanges, opts: SaveOptions) -> list:
    """Apply tag changes directly to `path` (used on freshly converted temp files)."""
    audio = open_audio(path)
    handler = handler_for(audio)
    if handler is None:
        raise CannotTagError("This format can't store tags.")
    warnings = handler.apply(changes)
    handler.save(path, opts)
    return warnings


def save(path: str, changes: TagChanges, opts: SaveOptions, *, expected=None,
         verify_audio: bool = True, preserve_mtime: bool = False) -> list:
    """Save tag changes without ever touching the audio data.

    The edit happens on a temporary copy that is verified (it must parse, and its
    audio packets must be bit-identical to the original) before it atomically
    replaces the original file.
    """
    if changes.is_empty():
        return []
    validate_fields(changes.fields)
    st = os.stat(path)
    if expected is not None and (st.st_size, st.st_mtime_ns) != tuple(expected):
        raise FileChangedError("The file was changed by another program. Reload it first.")
    if winfs.is_read_only(st):
        raise FileReadOnlyError("The file is read-only.")
    tmp = _temp_name(path)
    try:
        shutil.copyfile(path, tmp)
        warnings = write_tags(tmp, changes, opts)
        open_audio(tmp)  # must still parse
        if verify_audio and ffmpeg.available():
            if ffmpeg.audio_packet_md5(path) != ffmpeg.audio_packet_md5(tmp):
                raise IntegrityError("Safety check failed: the audio data would have changed. "
                                     "The original file was left untouched.")
        if preserve_mtime:
            os.utime(tmp, ns=(st.st_atime_ns, st.st_mtime_ns))
        winfs.replace_with_retry(tmp, path)
        winfs.restore_metadata(path, st)
        return warnings
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

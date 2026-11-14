"""Tag handlers for every supported container."""

from __future__ import annotations

from mutagen.aiff import AIFF
from mutagen.apev2 import APEv2File
from mutagen.asf import ASF
from mutagen.dsf import DSF
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.ogg import OggFileType
from mutagen.trueaudio import TrueAudio
from mutagen.wave import WAVE

from .ape import APEHandler
from .asf import ASFHandler
from .base import (FIELD_KEYS, MULTI_SEP, PICTURE_TYPES, Picture, SaveOptions, TagChanges,
                   TagError, TagHandler, TagSnapshot, empty_fields, validate_fields)
from .id3 import ID3Handler
from .mp4 import MP4Handler
from .vorbis import VorbisHandler

__all__ = [
    "FIELD_KEYS", "MULTI_SEP", "PICTURE_TYPES", "Picture", "SaveOptions", "TagChanges",
    "TagError", "TagHandler", "TagSnapshot", "empty_fields", "handler_for", "validate_fields",
]


def handler_for(audio) -> TagHandler | None:
    """Pick the tag handler for a mutagen file object, or None if it can't hold tags."""
    if isinstance(audio, (MP3, WAVE, AIFF, DSF, TrueAudio)):
        return ID3Handler(audio)
    if isinstance(audio, FLAC) or isinstance(audio, OggFileType):
        return VorbisHandler(audio)
    if isinstance(audio, MP4):
        return MP4Handler(audio)
    if isinstance(audio, ASF):
        return ASFHandler(audio)
    if isinstance(audio, APEv2File):
        return APEHandler(audio)
    return None

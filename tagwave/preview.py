"""Audio for the built-in player.

Formats the embedded browser engine can't decode (ALAC, AIFF, WMA, APE, WavPack...)
are decoded once into a temporary lossless FLAC/WAV used only for listening.
The original file is never modified.
"""

from __future__ import annotations

import hashlib
import os
import threading

from .core import ffmpeg

DIRECT = {
    ("MP3", "MP3"): "audio/mpeg",
    ("MP4", "AAC"): "audio/mp4",
    ("AAC (ADTS)", "AAC"): "audio/aac",
    ("FLAC", "FLAC"): "audio/flac",
    ("Ogg", "Vorbis"): "audio/ogg",
    ("Ogg", "Opus"): "audio/ogg",
    ("WAV", "PCM"): "audio/wav",
    ("WAV", "PCM (float)"): "audio/wav",
}


def direct_mime(info: dict) -> str | None:
    mime = DIRECT.get((info.get("container"), info.get("codec")))
    if mime and info.get("container") == "FLAC" and (info.get("bitsPerSample") or 16) > 24:
        return None
    if mime and (info.get("sampleRate") or 0) > 192000:
        return None
    return mime


class PreviewCache:
    def __init__(self, root: str):
        self.dir = os.path.join(root, "preview")
        os.makedirs(self.dir, exist_ok=True)
        self._locks: dict = {}
        self._guard = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def source(self, path: str, info: dict) -> tuple[str, str, bool]:
        """Return (file_to_stream, mime, transcoded)."""
        mime = direct_mime(info)
        if mime:
            return path, mime, False
        st = os.stat(path)
        key = hashlib.sha1(("%s|%d|%d" % (os.path.normcase(path), st.st_size, st.st_mtime_ns)).encode()).hexdigest()
        bits = info.get("bitsPerSample") or 16
        use_wav = bits > 24 or "float" in (info.get("codec") or "").lower()
        out = os.path.join(self.dir, key + (".wav" if use_wav else ".flac"))
        with self._lock_for(key):
            if not os.path.exists(out):
                tmp = out + ".part"
                args = [ffmpeg.ffmpeg_path(), "-v", "error", "-nostdin", "-y", "-i", path, "-map", "0:a:0",
                        "-map_metadata", "-1"]
                rate = info.get("sampleRate") or 0
                if rate > 192000 or info.get("codec") == "DSD":
                    args += ["-ar", "88200" if rate % 44100 == 0 else "96000"]
                if use_wav:
                    args += ["-c:a", "pcm_f32le", "-f", "wav", tmp]
                else:
                    fmt = ["-sample_fmt", "s16"] if bits <= 16 else ["-sample_fmt", "s32"]
                    args += ["-c:a", "flac", "-compression_level", "0", *fmt, "-f", "flac", tmp]
                res = ffmpeg.run(args, timeout=600)
                if res.returncode != 0:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                    raise ffmpeg.FFmpegError(res.stderr.strip() or "preview failed")
                os.replace(tmp, out)
        return out, ("audio/wav" if use_wav else "audio/flac"), True

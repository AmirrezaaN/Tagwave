"""Format conversion that always takes the least destructive path.

Order of preference for every file:
  1. copy-file : target is the same format  -> the file is copied, only tags change
  2. remux     : same lossy codec, different container -> packets copied, no re-encode
  3. lossless  : (lossless or lossy) -> lossless target, sample rate/bit depth preserved,
                 and lossless->lossless is verified bit-perfect by comparing decoded PCM
  4. lossy     : only when the user picked a lossy target; highest quality settings
"""

from __future__ import annotations

import os
import re
import secrets
import shutil
import subprocess
import threading
from dataclasses import dataclass, field

from . import audiofile, ffmpeg
from .errors import TagwaveError
from .tags import SaveOptions, TagChanges, TagError

TARGETS = {
    "flac": {"ext": ".flac", "codec": "flac", "lossless": True, "muxer": "flac"},
    "alac": {"ext": ".m4a", "codec": "alac", "lossless": True, "muxer": "ipod"},
    "wav": {"ext": ".wav", "codec": "pcm", "lossless": True, "muxer": "wav"},
    "aiff": {"ext": ".aiff", "codec": "pcm", "lossless": True, "muxer": "aiff"},
    "mp3": {"ext": ".mp3", "codec": "mp3", "lossless": False, "muxer": "mp3"},
    "aac": {"ext": ".m4a", "codec": "aac", "lossless": False, "muxer": "ipod"},
    "opus": {"ext": ".opus", "codec": "opus", "lossless": False, "muxer": "opus"},
    "ogg": {"ext": ".ogg", "codec": "vorbis", "lossless": False, "muxer": "ogg"},
}

# quality id -> ffmpeg args (first entry is the default = best)
QUALITY = {
    "mp3": {"320": ["-b:a", "320k"], "v0": ["-q:a", "0"], "256": ["-b:a", "256k"], "192": ["-b:a", "192k"]},
    "aac": {"320": ["-b:a", "320k"], "256": ["-b:a", "256k"], "192": ["-b:a", "192k"]},
    "opus": {"320": ["-b:a", "320k"], "510": ["-b:a", "510k"], "256": ["-b:a", "256k"], "192": ["-b:a", "192k"]},
    "ogg": {"q10": ["-q:a", "10"], "q8": ["-q:a", "8"], "q6": ["-q:a", "6"]},
}

LOSSLESS_CODECS = {"flac", "alac", "wavpack", "ape", "tta", "wmalossless", "mlp", "truehd", "tak"}
FLOAT_FMTS = {"flt", "fltp", "dbl", "dblp"}


class ConversionError(TagwaveError):
    code = "conversion-failed"


class Cancelled(TagwaveError):
    code = "cancelled"


@dataclass
class ConvertOptions:
    target: str
    quality: str | None = None
    flac_level: int = 8
    out_dir: str | None = None       # None -> next to the source file
    overwrite: str = "rename"        # rename | overwrite | skip
    verify: bool = True
    tag_opts: SaveOptions = field(default_factory=SaveOptions)


@dataclass
class Source:
    path: str
    container: str
    codec: str               # ffmpeg codec name
    sample_fmt: str
    sample_rate: int
    channels: int
    bits: int | None
    is_float: bool
    lossless: bool
    duration: float


@dataclass
class Plan:
    mode: str                 # copy-file | remux | lossless | lossy | unsupported
    bit_perfect: bool
    verify_pcm: str | None    # sample format used to prove bit-perfection, or None
    warnings: list
    args: list
    out_rate: int
    out_bits: int | None
    out_channels: int
    out_codec: str

    def to_json(self) -> dict:
        return {"mode": self.mode, "bitPerfect": self.bit_perfect, "warnings": self.warnings,
                "sampleRate": self.out_rate, "bits": self.out_bits, "channels": self.out_channels,
                "codec": self.out_codec, "verified": bool(self.verify_pcm)}


def analyze_source(path: str, info: dict) -> Source:
    pr = ffmpeg.probe(path)
    s = pr["stream"]
    fmt = s.get("sample_fmt", "") or ""
    codec = s.get("codec_name", "") or ""
    bits = 0
    for key in ("bits_per_raw_sample", "bits_per_sample"):
        try:
            bits = int(s.get(key) or 0)
        except ValueError:
            bits = 0
        if bits:
            break
    if not bits and fmt.startswith("s16"):
        bits = 16
    if not bits and fmt.startswith("s32"):
        bits = 32
    if not bits and fmt.startswith("u8"):
        bits = 8
    is_float = fmt in FLOAT_FMTS
    lossless = bool(info.get("lossless")) or codec in LOSSLESS_CODECS or codec.startswith("pcm_")
    if codec.startswith("dsd_"):
        lossless = True
    try:
        duration = float(pr["format"].get("duration") or info.get("duration") or 0)
    except ValueError:
        duration = float(info.get("duration") or 0)
    return Source(path=path, container=info.get("container", ""), codec=codec, sample_fmt=fmt,
                  sample_rate=int(s.get("sample_rate") or 0), channels=int(s.get("channels") or 0),
                  bits=bits or None, is_float=is_float, lossless=lossless, duration=duration)


def _same_format(src: Source, target: str) -> bool:
    c, k = src.container, src.codec
    return ((target == "mp3" and c == "MP3") or
            (target == "flac" and c == "FLAC") or
            (target == "aac" and c == "MP4" and k == "aac") or
            (target == "alac" and c == "MP4" and k == "alac") or
            (target == "opus" and c == "Ogg" and k == "opus") or
            (target == "ogg" and c == "Ogg" and k == "vorbis") or
            (target == "wav" and c == "WAV" and k.startswith("pcm_")) or
            (target == "aiff" and c == "AIFF" and k.startswith("pcm_")))


def _lossy_rate(rate: int, allowed_max: int = 48000) -> int:
    if rate <= allowed_max:
        return rate
    return 44100 if rate % 44100 == 0 else 48000


def make_plan(src: Source, opts: ConvertOptions) -> Plan:
    t = opts.target
    if t not in TARGETS:
        raise ConversionError("Unknown output format.")
    spec = TARGETS[t]
    warnings: list = []
    rate, ch = src.sample_rate, src.channels

    if _same_format(src, t):
        return Plan("copy-file", True, None, [], [], rate, src.bits, ch, src.codec)

    if not spec["lossless"] and src.codec == spec["codec"]:
        return Plan("remux", True, None, [], ["-c:a", "copy"], rate, None, ch, src.codec)

    if src.codec in ("", "none") or src.container == "OptimFROG":
        return Plan("unsupported", False, None, ["no-decoder"], [], rate, None, ch, "")

    dsd = src.codec.startswith("dsd_")
    if dsd:
        warnings.append("dsd-to-pcm")

    if spec["lossless"]:
        if not src.lossless:
            warnings.append("lossy-to-lossless")
        args: list = []
        bits: int | None
        verify = None
        bit_perfect = src.lossless and not dsd
        if src.is_float or dsd:
            if t in ("wav", "aiff") and src.lossless and not dsd:
                dbl = src.sample_fmt.startswith("dbl")
                pcm = ("pcm_f64" if dbl else "pcm_f32") + ("le" if t == "wav" else "be")
                args = ["-c:a", pcm]
                bits = 64 if dbl else 32
                verify = "f64le" if dbl else "f32le"
            else:
                bits = 24
                if src.lossless and not dsd:
                    warnings.append("float-to-int")
                    bit_perfect = False
                elif dsd:
                    bit_perfect = False
                else:
                    bit_perfect = False   # decoded lossy audio; no *additional* loss
        else:
            bits = src.bits or 16
            verify = "s32le" if src.lossless else None

        if t == "flac":
            fmt_args = ["-sample_fmt", "s16"] if bits <= 16 else ["-sample_fmt", "s32", "-bits_per_raw_sample", str(min(bits, 32))]
            if bits > 24:
                fmt_args += ["-strict", "experimental"]
            args = ["-c:a", "flac", "-compression_level", str(max(0, min(12, opts.flac_level)))] + fmt_args
        elif t == "alac":
            if bits > 24:
                warnings.append("bit-depth-reduced")
                bits, bit_perfect, verify = 24, False, None
            args = ["-c:a", "alac"] + (["-sample_fmt", "s16p"] if bits <= 16 else
                                       ["-sample_fmt", "s32p", "-bits_per_raw_sample", str(bits)])
        elif not args:  # integer PCM
            le = t == "wav"
            if bits <= 8 and le:
                codec = "pcm_u8"
            elif bits <= 16:
                codec = "pcm_s16"
            elif bits <= 24:
                codec = "pcm_s24"
            else:
                codec = "pcm_s32"
            if codec != "pcm_u8":
                codec += "le" if le else "be"
            args = ["-c:a", codec]
        if t == "wav":
            args += ["-rf64", "auto"]
        if not bit_perfect:
            verify = None
        return Plan("lossless", bit_perfect, verify, warnings, args, rate, bits, ch, spec["codec"])

    # ---- lossy target
    warnings.append("lossless-to-lossy" if src.lossless else "lossy-to-lossy")
    qual = QUALITY[t]
    qid = opts.quality if opts.quality in qual else next(iter(qual))
    args = []
    out_rate = rate
    if t == "mp3":
        out_rate = _lossy_rate(rate)
        if ch > 2:
            warnings.append("downmix")
            ch = 2
        args = ["-c:a", "libmp3lame"] + qual[qid] + ["-id3v2_version", "0", "-write_xing", "1"]
    elif t == "aac":
        out_rate = _lossy_rate(rate)
        q = list(qual[qid])
        if q[0] == "-b:a" and ch > 2:   # scale bitrate per channel pair for surround
            q[1] = "%dk" % (int(q[1][:-1]) * ch // 2)
        args = ["-c:a", "aac", "-aac_coder", "twoloop"] + q
    elif t == "opus":
        out_rate = 48000
        q = list(qual[qid])
        if ch > 2:
            q[1] = "%dk" % min(256 * ch, int(q[1][:-1]) * ch // 2)
        args = ["-c:a", "libopus", "-vbr", "on", "-compression_level", "10",
                "-application", "audio"] + q
        if ch > 2:
            args += ["-mapping_family", "1"]
    elif t == "ogg":
        out_rate = _lossy_rate(rate)
        args = ["-c:a", "libvorbis"] + qual[qid]
    if out_rate != rate:
        warnings.append("resample")
    args += ["-af", "aresample=%d:filter_size=64:phase_shift=10:cutoff=0.97" % out_rate]
    if ch != src.channels:
        args += ["-ac", str(ch)]
    return Plan("lossy", False, None, warnings, args, out_rate, None, ch, spec["codec"])


# ------------------------------------------------------------------ output naming

_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_name_lock = threading.Lock()
_reserved: set = set()


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p))


def output_path(src_path: str, opts: ConvertOptions, stem: str | None = None,
                reserve: bool = True) -> tuple[str, str]:
    """Pick and reserve the output path.

    Returns (path, action) where action is "new", "overwrite" or "skip".
    The source file itself is never a valid destination.
    """
    ext = TARGETS[opts.target]["ext"]
    out_dir = opts.out_dir or os.path.dirname(src_path)
    stem = _INVALID.sub("_", stem or os.path.splitext(os.path.basename(src_path))[0]).strip() or "audio"
    cand = os.path.join(out_dir, stem + ext)
    src_n = _norm(src_path)
    with _name_lock:
        def taken(p):
            n = _norm(p)
            return n == src_n or n in _reserved or os.path.exists(p)
        cand_n = _norm(cand)
        if cand_n != src_n and cand_n not in _reserved and os.path.exists(cand):
            if opts.overwrite == "overwrite":
                if reserve:
                    _reserved.add(cand_n)
                return cand, "overwrite"
            if opts.overwrite == "skip":
                return cand, "skip"
        i = 1
        while taken(cand):
            cand = os.path.join(out_dir, "%s (%d)%s" % (stem, i, ext))
            i += 1
        if reserve:
            _reserved.add(_norm(cand))
        return cand, "new"


def release_name(path: str) -> None:
    with _name_lock:
        _reserved.discard(_norm(path))


# ------------------------------------------------------------------ running

def _safe_tag_write(path: str, changes: TagChanges, opts: SaveOptions) -> list:
    """Write tags to a fresh output; drop custom fields the target format can't store."""
    dropped = []
    custom = list(changes.custom or [])
    for _ in range(len(custom) + 1):
        try:
            audiofile.write_tags(path, TagChanges(dict(changes.fields), custom, changes.pictures), opts)
            return ["custom-dropped:" + k for k in dropped]
        except TagError as exc:
            bad = exc.field
            if not bad or bad not in [k for k, _ in custom]:
                raise
            custom = [c for c in custom if c[0] != bad]
            dropped.append(bad)
    raise ConversionError("Could not write tags.")


def convert(src: Source, plan: Plan, out_path: str, tags: TagChanges, opts: ConvertOptions,
            progress=None, cancel: threading.Event | None = None) -> dict:
    """Run one conversion. Returns {'path', 'verified', 'warnings'}."""
    if plan.mode == "unsupported":
        raise ConversionError("This file's audio can't be decoded.", "no-decoder")
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    ext = os.path.splitext(out_path)[1]
    tmp = os.path.join(out_dir, ".%s.tagwave-%s%s" % (
        os.path.splitext(os.path.basename(out_path))[0][:80], secrets.token_hex(4), ext))
    warnings = list(plan.warnings)
    verified = False
    try:
        if plan.mode == "copy-file":
            shutil.copyfile(src.path, tmp)
            if progress:
                progress(1.0)
        else:
            _run_ffmpeg(src, plan, tmp, TARGETS[opts.target]["muxer"], progress, cancel)
        if cancel is not None and cancel.is_set():
            raise Cancelled("Cancelled")
        if tags is not None:
            warnings += _safe_tag_write(tmp, tags, opts.tag_opts)
        if opts.verify and plan.verify_pcm:
            if ffmpeg.pcm_md5(src.path, plan.verify_pcm) != ffmpeg.pcm_md5(tmp, plan.verify_pcm):
                raise ConversionError("Verification failed: the output is not bit-identical.",
                                      "verify-failed")
            verified = True
        elif opts.verify and plan.mode == "copy-file":
            verified = ffmpeg.audio_packet_md5(src.path) == ffmpeg.audio_packet_md5(tmp)
            if not verified:
                raise ConversionError("Verification failed.", "verify-failed")
        os.replace(tmp, out_path)
        return {"path": out_path, "verified": verified, "warnings": warnings}
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _run_ffmpeg(src: Source, plan: Plan, tmp: str, muxer: str, progress, cancel) -> None:
    cmd = [ffmpeg.ffmpeg_path(), "-hide_banner", "-v", "error", "-nostdin", "-y",
           "-i", src.path, "-map", "0:a:0", "-map_metadata", "-1", "-map_chapters", "-1",
           "-fflags", "+bitexact", *plan.args, "-progress", "pipe:1", "-nostats",
           "-f", muxer, tmp]
    proc = ffmpeg.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                        encoding="utf-8", errors="replace")
    err_lines: list = []

    def drain_err():
        for line in proc.stderr:
            if len(err_lines) < 50:
                err_lines.append(line.rstrip())

    t = threading.Thread(target=drain_err, daemon=True)
    t.start()
    total_us = max(1.0, src.duration * 1_000_000)
    try:
        for line in proc.stdout:
            if cancel is not None and cancel.is_set():
                proc.kill()
                break
            if line.startswith("out_time_us=") and progress:
                try:
                    progress(min(0.99, max(0.0, int(line.split("=", 1)[1]) / total_us)))
                except ValueError:
                    pass
        proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        t.join(timeout=2)
    if cancel is not None and cancel.is_set():
        raise Cancelled("Cancelled")
    if proc.returncode != 0:
        raise ConversionError("FFmpeg failed: " + (" ".join(err_lines[-3:]) or "unknown error"))
    if progress:
        progress(1.0)

import io
import os
import shutil
import subprocess
import sys

import pytest
from PIL import Image, ImageCms

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tagwave.core import ffmpeg  # noqa: E402

# A short stereo test signal with noise so that 24-bit samples use all bits.
SIGNAL = ("aevalsrc=exprs='0.45*sin(2*PI*440*t)+0.05*random(0)|0.45*sin(2*PI*660*t)+0.05*random(1)'"
          ":s={rate}:d={dur}")

# name -> (extension, encoder args, sample rate)
SAMPLES = {
    "mp3": (".mp3", ["-c:a", "libmp3lame", "-b:a", "192k"], 44100),
    "flac16": (".flac", ["-c:a", "flac", "-sample_fmt", "s16"], 44100),
    "flac24": (".flac", ["-c:a", "flac", "-sample_fmt", "s32", "-bits_per_raw_sample", "24"], 96000),
    "aac": (".m4a", ["-c:a", "aac", "-b:a", "192k"], 44100),
    "alac": (".m4a", ["-c:a", "alac", "-sample_fmt", "s16p"], 44100),
    "alac24": (".m4a", ["-c:a", "alac", "-sample_fmt", "s32p", "-bits_per_raw_sample", "24"], 48000),
    "vorbis": (".ogg", ["-c:a", "libvorbis", "-q:a", "5"], 44100),
    "opus": (".opus", ["-c:a", "libopus", "-b:a", "128k"], 48000),
    "wav16": (".wav", ["-c:a", "pcm_s16le"], 44100),
    "wav24": (".wav", ["-c:a", "pcm_s24le"], 48000),
    "wavf32": (".wav", ["-c:a", "pcm_f32le"], 44100),
    "aiff": (".aiff", ["-c:a", "pcm_s16be"], 44100),
    "wma": (".wma", ["-c:a", "wmav2", "-b:a", "128k"], 44100),
    "wavpack": (".wv", ["-c:a", "wavpack", "-sample_fmt", "s16p"], 44100),
    "tta": (".tta", ["-c:a", "tta", "-sample_fmt", "s16"], 44100),
    "adts": (".aac", ["-c:a", "aac", "-b:a", "128k", "-f", "adts"], 44100),
}

TAGGABLE = [k for k in SAMPLES if k != "adts"]


@pytest.fixture(scope="session")
def sample_dir(tmp_path_factory):
    if not ffmpeg.available():
        pytest.skip("ffmpeg not available")
    d = tmp_path_factory.mktemp("samples")
    for name, (ext, args, rate) in SAMPLES.items():
        out = d / (name + ext)
        cmd = [ffmpeg.ffmpeg_path(), "-v", "error", "-y", "-f", "lavfi",
               "-i", SIGNAL.format(rate=rate, dur=3), *args, str(out)]
        subprocess.run(cmd, check=True, creationflags=ffmpeg.CREATE_NO_WINDOW)
    return d


@pytest.fixture
def sample(sample_dir, tmp_path):
    """Return a function giving a fresh, writable copy of a generated sample."""
    def get(name):
        ext = SAMPLES[name][0]
        dst = tmp_path / ("copy_%s%s" % (name, ext))
        shutil.copyfile(sample_dir / (name + ext), dst)
        return str(dst)
    return get


def make_jpeg(w=600, h=600, color=(200, 40, 90), icc=True, subsampling=2, progressive=False):
    im = Image.new("RGB", (w, h), color)
    for x in range(0, w, 7):
        for y in range(0, h, 11):
            im.putpixel((x, y), ((x * 3) % 255, (y * 5) % 255, (x + y) % 255))
    out = io.BytesIO()
    params = {"quality": 92, "subsampling": subsampling, "progressive": progressive}
    if icc:
        params["icc_profile"] = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    im.save(out, "JPEG", **params)
    return out.getvalue()


def make_png(w=300, h=200, alpha=True):
    im = Image.new("RGBA" if alpha else "RGB", (w, h), (10, 120, 200, 180) if alpha else (10, 120, 200))
    for x in range(0, w, 5):
        im.putpixel((x, x % h), (255, 255, 0, 255) if alpha else (255, 255, 0))
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


@pytest.fixture(scope="session")
def jpeg_bytes():
    return make_jpeg()


@pytest.fixture(scope="session")
def png_bytes():
    return make_png()

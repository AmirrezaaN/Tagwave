import os
import subprocess

import pytest

from tagwave.core import audiofile, ffmpeg, quality

NOISE = "anoisesrc=color=pink:amplitude=0.3:r={rate}:d=12:seed={seed}"


def _ff(*args):
    subprocess.run([ffmpeg.ffmpeg_path(), "-v", "error", "-y", *args], check=True,
                   creationflags=ffmpeg.CREATE_NO_WINDOW)


@pytest.fixture(scope="module")
def qdir(tmp_path_factory):
    if not ffmpeg.available():
        pytest.skip("ffmpeg not available")
    d = tmp_path_factory.mktemp("quality")
    stereo = "[0][1]amerge=inputs=2"
    # Genuine full-band 44.1 kHz stereo
    _ff("-f", "lavfi", "-i", NOISE.format(rate=44100, seed=1), "-f", "lavfi", "-i", NOISE.format(rate=44100, seed=2),
        "-filter_complex", stereo, "-c:a", "flac", "-sample_fmt", "s16", str(d / "genuine.flac"))
    # 128 kbps MP3 decoded and stored as FLAC (fake lossless)
    _ff("-i", str(d / "genuine.flac"), "-c:a", "libmp3lame", "-b:a", "128k", str(d / "lq.mp3"))
    _ff("-i", str(d / "lq.mp3"), "-c:a", "flac", "-sample_fmt", "s16", str(d / "fake.flac"))
    # 44.1 kHz upsampled to 96 kHz/24-bit (fake hi-res)
    _ff("-i", str(d / "genuine.flac"), "-af", "aresample=96000", "-c:a", "flac", "-sample_fmt", "s32",
        "-bits_per_raw_sample", "24", str(d / "upsampled.flac"))
    # 16-bit audio padded into a 24-bit container
    _ff("-i", str(d / "genuine.flac"), "-c:a", "pcm_s24le", str(d / "padded.wav"))
    # Real 24-bit noise
    _ff("-f", "lavfi", "-i", NOISE.format(rate=48000, seed=3), "-f", "lavfi", "-i", NOISE.format(rate=48000, seed=4),
        "-filter_complex", stereo, "-c:a", "pcm_s24le", str(d / "real24.wav"))
    # Dual-mono
    _ff("-f", "lavfi", "-i", NOISE.format(rate=44100, seed=5), "-ac", "2", "-c:a", "flac", str(d / "mono.flac"))
    return d


def _music(path, rate=44100, dur=10):
    """Sparse, music-like stereo signal: harmonic chords, kicks and bright hi-hats."""
    import wave

    import numpy as np
    rng = np.random.default_rng(3)
    t = np.arange(rate * dur) / rate
    y = np.zeros(len(t))
    for i, f0 in enumerate((110, 147, 165, 131)):
        a, b = int(i * 2.5 * rate), int((i + 1) * 2.5 * rate)
        seg = t[a:b] - t[a]
        for h in range(1, 14):
            y[a:b] += 0.06 / h * np.sin(2 * np.pi * f0 * h * seg) * np.exp(-seg * 0.5)
    for k in range(int(dur / 0.27)):
        p = int(k * 0.27 * rate)
        n = min(int(0.05 * rate), len(t) - p)
        hat = np.diff(np.concatenate([[0], rng.standard_normal(n)]))
        y[p:p + n] += hat * np.exp(-np.arange(n) / rate * 60) * 0.08
    y = (y / np.max(np.abs(y)) * 0.8 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(y, 2).tobytes())


def test_fake_lossless_with_sparse_music(qdir):
    src = qdir / "music.wav"
    _music(src)
    _ff("-i", str(src), "-c:a", "libmp3lame", "-b:a", "128k", str(qdir / "music.mp3"))
    _ff("-i", str(qdir / "music.mp3"), "-c:a", "flac", "-sample_fmt", "s16", str(qdir / "music_fake.flac"))
    _ff("-i", str(src), "-c:a", "flac", str(qdir / "music_real.flac"))
    fake = _analyze(qdir / "music_fake.flac")
    assert fake["verdict"] == "lossy-source", fake
    assert _analyze(qdir / "music_real.flac")["verdict"] == "good"


def _analyze(path, png=None):
    return quality.analyze(str(path), audiofile.load(str(path)).info, png)


def test_genuine_lossless(qdir, tmp_path):
    png = str(tmp_path / "s.png")
    r = _analyze(qdir / "genuine.flac", png)
    assert r["verdict"] == "good", r
    assert os.path.getsize(png) > 10000


def test_fake_lossless_from_mp3(qdir):
    r = _analyze(qdir / "fake.flac")
    assert r["verdict"] == "lossy-source", r
    assert 15000 < r["cutoffHz"] < 18500 and r["estimatedKbps"] in ("128", "160")


def test_lossy_file_gets_estimate(qdir):
    r = _analyze(qdir / "lq.mp3")
    assert r["verdict"] == "lossy" and r["estimatedKbps"] in ("128", "160"), r


def test_fake_hires(qdir):
    r = _analyze(qdir / "upsampled.flac")
    assert r["verdict"] == "upsampled", r
    assert "from-48k" in r["notes"]


def test_padded_24bit(qdir):
    r = _analyze(qdir / "padded.wav")
    assert r["verdict"] == "padded-bits" and r["effectiveBits"] == 16, r


def test_real_24bit(qdir):
    r = _analyze(qdir / "real24.wav")
    assert r["verdict"] == "good" and r["effectiveBits"] == 24, r


def test_mono_content(qdir):
    assert "mono-content" in _analyze(qdir / "mono.flac")["notes"]

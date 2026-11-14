"""'Real quality' analysis: spectrogram plus automatic detection of

* lossy sources hiding in lossless files (a hard frequency cut-off, e.g. 16 kHz),
* fake hi-res (96 kHz files with nothing above 22 kHz),
* fake 24-bit (24-bit files whose low 8 bits are always zero),
* stereo files that are really mono.

Results are heuristics and are phrased as "likely" in the UI.
"""

from __future__ import annotations

import subprocess

import numpy as np

from . import ffmpeg

MAX_SECONDS = 600
FFT = 4096


def spectrogram_png(path: str, out_png: str, width: int = 1600, height: int = 600) -> None:
    """Bare spectrogram (time → x, 0 Hz at the bottom → Nyquist at the top).

    Axes and labels are drawn by the UI so they match the theme and language.
    """
    flt = ("[0:a:0]showspectrumpic=s=%dx%d:legend=0:mode=combined:color=intensity:scale=log:"
           "fscale=lin:win_func=hann:drange=120" % (width, height))
    res = ffmpeg.run([ffmpeg.ffmpeg_path(), "-v", "error", "-nostdin", "-y", "-t", str(MAX_SECONDS),
                      "-i", path, "-lavfi", flt, "-frames:v", "1", "-c:v", "png", "-f", "image2",
                      out_png], timeout=300)
    if res.returncode != 0:
        raise ffmpeg.FFmpegError(res.stderr.strip() or "spectrogram failed")


def _stream_pcm(path: str, fmt: str, channels: int, dtype, block: int):
    cmd = [ffmpeg.ffmpeg_path(), "-v", "error", "-nostdin", "-t", str(MAX_SECONDS), "-i", path,
           "-map", "0:a:0", "-ac", str(channels), "-f", fmt, "-c:a", "pcm_" + fmt, "-"]
    proc = ffmpeg.popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    item = np.dtype(dtype).itemsize * channels
    try:
        while True:
            buf = proc.stdout.read(block * item)
            if not buf:
                break
            usable = len(buf) - len(buf) % item
            yield np.frombuffer(buf[:usable], dtype=dtype).reshape(-1, channels)
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def average_spectrum(path: str, channels: int) -> tuple[np.ndarray, bool]:
    """Mean power spectrum (dB) of the mid channel, and whether L == R everywhere."""
    ch = 2 if channels >= 2 else 1
    window = np.hanning(FFT).astype(np.float32)
    acc = np.zeros(FFT // 2 + 1, np.float64)
    frames = 0
    identical = ch == 2
    carry = np.zeros((0, ch), np.float32)
    for chunk in _stream_pcm(path, "f32le", ch, np.float32, FFT * 64):
        if ch == 2 and identical and np.max(np.abs(chunk[:, 0] - chunk[:, 1]), initial=0) > 1e-6:
            identical = False
        data = np.concatenate([carry, chunk]) if len(carry) else chunk
        n = len(data) // FFT
        if n:
            mid = data[: n * FFT].mean(axis=1).reshape(n, FFT) * window
            acc += (np.abs(np.fft.rfft(mid, axis=1)) ** 2).sum(axis=0)
            frames += n
        carry = data[n * FFT:]
    if frames == 0:
        return np.full(FFT // 2 + 1, -200.0), identical
    return 10 * np.log10(acc / frames + 1e-20), identical


def find_cutoff(spec_db: np.ndarray, sample_rate: int) -> float | None:
    """Frequency of a hard low-pass 'cliff', or None if the spectrum reaches Nyquist."""
    nyq = sample_rate / 2
    hz_per_bin = nyq / (len(spec_db) - 1)
    band = max(1, int(round(100 / hz_per_bin)))   # 100 Hz bands
    nb = len(spec_db) // band
    bands = spec_db[: nb * band].reshape(nb, band).mean(axis=1)
    freqs = (np.arange(nb) + 0.5) * band * hz_per_bin
    music = bands[(freqs > 500) & (freqs < 5000)]
    if not len(music):
        return None
    bands = np.maximum(bands, -140.0)                      # digital silence -> fixed floor
    music = np.maximum(music, -140.0)
    floor = float(np.median(bands[-max(3, nb // 50):]))   # level right below Nyquist
    gap = float(np.median(music)) - floor
    if gap < 15:
        return None          # content (or noise) all the way up: full bandwidth
    # Highest band still clearly above the floor (relative threshold, so filter
    # ripples down in the floor don't count as content).
    above = np.nonzero(bands > floor + max(6.0, 0.3 * gap))[0]
    if not len(above):
        return None
    top = int(above[-1])
    cut = float(freqs[top]) + band * hz_per_bin / 2
    if cut > nyq * 0.97:
        return None
    # Nothing substantial may come back above the cut (that would not be a low-pass)...
    rest = bands[top + 2:]
    if len(rest) and float(np.max(rest)) > floor + 0.5 * gap:
        return None
    # ...and the drop must be steep, unlike the gentle roll-off of real recordings.
    below = bands[(freqs > cut - 1600) & (freqs < cut - 300)]
    if not len(below) or float(np.median(below)) - floor < 15:
        return None
    return cut


def effective_bits(path: str, declared: int | None, channels: int) -> int | None:
    if not declared or declared <= 16:
        return declared
    ch = max(1, min(channels, 8))
    acc = 0
    for chunk in _stream_pcm(path, "s32le", ch, np.int32, 1 << 18):
        acc |= int(np.bitwise_or.reduce(chunk.ravel().view(np.uint32), initial=0))
        if acc & 0xFFFF:   # bits below 16-bit precision in use -> genuinely > 16-bit
            break
    if acc == 0:
        return declared
    tz = (acc & -acc).bit_length() - 1      # trailing zero bits in the 32-bit container
    return max(1, min(declared, 32 - tz))


def estimate_lossy_source(cut_hz: float) -> str:
    """Typical encoder low-pass points (LAME 3.100: 128k≈17 kHz, 192k≈18.6 kHz, 320k≈20.5 kHz)."""
    k = cut_hz / 1000
    for limit, kbps in ((13.5, "64"), (15.8, "96"), (17.25, "128"), (18.0, "160"), (19.0, "192"), (19.85, "256")):
        if k < limit:
            return kbps
    return "320"


def analyze(path: str, info: dict, spectrogram_out: str | None = None) -> dict:
    stream = ffmpeg.probe(path)["stream"]
    rate = int(stream.get("sample_rate") or info.get("sampleRate") or 44100)
    channels = int(stream.get("channels") or info.get("channels") or 2)
    if spectrogram_out:
        spectrogram_png(path, spectrogram_out)
    spec, identical = average_spectrum(path, channels)
    cut = find_cutoff(spec, rate)
    lossless = bool(info.get("lossless"))
    declared = info.get("bitsPerSample") if lossless else None
    fmt = stream.get("sample_fmt", "")
    eff = effective_bits(path, declared, channels) if lossless and fmt not in ("flt", "fltp", "dbl", "dblp") else declared

    notes = []
    estimate = None
    nyq = rate / 2
    padded = bool(eff and declared and eff < declared)
    if padded:
        notes.append("padded-bits")
    if identical:
        notes.append("mono-content")
    if not lossless:
        verdict = "lossy"
        if cut is not None:
            estimate = estimate_lossy_source(cut)
    elif cut is not None and cut <= 20800:
        verdict = "lossy-source"
        estimate = estimate_lossy_source(cut)
    elif rate > 48000 and cut is not None and (cut <= 30000 or (rate > 96000 and cut <= 52000)):
        verdict = "upsampled"
        notes.append("from-48k" if cut <= 30000 else "from-96k")
    elif padded:
        verdict = "padded-bits"
    else:
        verdict = "good"
    return {
        "verdict": verdict,
        "cutoffHz": round(cut) if cut else None,
        "nyquistHz": round(nyq),
        "sampleRate": rate,
        "estimatedKbps": estimate,
        "declaredBits": declared,
        "effectiveBits": eff,
        "notes": notes,
        "lossless": lossless,
    }

import json
import os
import subprocess

import pytest
from conftest import SIGNAL

from tagwave.core import audiofile, convert, ffmpeg
from tagwave.core.tags import Picture, TagChanges

LOSSLESS_SOURCES = ["flac16", "flac24", "alac", "alac24", "wav16", "wav24", "aiff", "wavpack", "tta"]
LOSSLESS_TARGETS = ["flac", "alac", "wav", "aiff"]


def _tags(jpeg):
    fields = {k: "" for k in ("title", "artist", "album")}
    fields.update(title="عنوان", artist="Artist", album="Album")
    return TagChanges(fields=fields, custom=[["MOOD", "happy"]], pictures=[Picture(3, "image/jpeg", "", jpeg)])


def _probe(path):
    return ffmpeg.probe(path)["stream"]


def _bits(stream):
    return int(stream.get("bits_per_raw_sample") or stream.get("bits_per_sample") or 0)


def _run(src_path, target, tmp_path, jpeg, **kw):
    loaded = audiofile.load(src_path)
    src = convert.analyze_source(src_path, loaded.info)
    opts = convert.ConvertOptions(target=target, out_dir=str(tmp_path / "out"), **kw)
    plan = convert.make_plan(src, opts)
    out, action = convert.output_path(src_path, opts)
    try:
        res = convert.convert(src, plan, out, _tags(jpeg), opts)
    finally:
        convert.release_name(out)
    return src, plan, res


@pytest.mark.parametrize("target", LOSSLESS_TARGETS)
@pytest.mark.parametrize("name", LOSSLESS_SOURCES)
def test_lossless_conversions_are_bit_perfect(sample, tmp_path, jpeg_bytes, name, target):
    src_path = sample(name)
    src, plan, res = _run(src_path, target, tmp_path, jpeg_bytes)
    assert plan.bit_perfect, (name, target, plan)
    if plan.mode != "copy-file":
        assert res["verified"], (name, target)
        # independent re-check
        assert ffmpeg.pcm_md5(src_path) == ffmpeg.pcm_md5(res["path"])
    out = _probe(res["path"])
    assert int(out["sample_rate"]) == src.sample_rate
    assert int(out["channels"]) == src.channels
    if target != "wav" or src.bits != 24:
        assert _bits(out) in (src.bits, 0) or _bits(out) >= src.bits
    snap = audiofile.load(res["path"]).snapshot
    assert snap.fields["title"] == "عنوان"
    assert snap.pictures[0].data == jpeg_bytes
    assert os.path.exists(src_path)


def test_float_wav_to_wav_and_flac(sample, tmp_path, jpeg_bytes):
    src_path = sample("wavf32")
    _, plan, res = _run(src_path, "aiff", tmp_path, jpeg_bytes)
    assert plan.bit_perfect and res["verified"]
    _, plan, res = _run(src_path, "flac", tmp_path, jpeg_bytes)
    assert not plan.bit_perfect and "float-to-int" in plan.warnings
    assert _bits(_probe(res["path"])) == 24


def test_32bit_integer_to_flac(tmp_path, jpeg_bytes):
    src_path = str(tmp_path / "s32.wav")
    subprocess.run([ffmpeg.ffmpeg_path(), "-v", "error", "-f", "lavfi", "-i",
                    SIGNAL.format(rate=44100, dur=2), "-c:a", "pcm_s32le", src_path], check=True)
    _, plan, res = _run(src_path, "flac", tmp_path, jpeg_bytes)
    assert plan.bit_perfect and res["verified"]
    _, plan, res = _run(src_path, "alac", tmp_path, jpeg_bytes)
    assert "bit-depth-reduced" in plan.warnings and not plan.bit_perfect


@pytest.mark.parametrize("target,codec", [("mp3", "mp3"), ("aac", "aac"), ("opus", "opus"), ("ogg", "vorbis")])
def test_lossless_to_lossy_best_quality(sample, tmp_path, jpeg_bytes, target, codec):
    src_path = sample("flac24")   # 96 kHz source
    _, plan, res = _run(src_path, target, tmp_path, jpeg_bytes)
    assert plan.mode == "lossy" and "lossless-to-lossy" in plan.warnings
    out = _probe(res["path"])
    assert out["codec_name"] == codec
    assert int(out["sample_rate"]) in (48000, 44100)
    assert "resample" in plan.warnings
    snap = audiofile.load(res["path"]).snapshot
    assert snap.fields["album"] == "Album" and snap.pictures[0].data == jpeg_bytes


def test_mp3_is_320_cbr(sample, tmp_path, jpeg_bytes):
    _, _, res = _run(sample("wav16"), "mp3", tmp_path, jpeg_bytes)
    info = audiofile.load(res["path"]).info
    assert info["bitrate"] == 320000 and info["bitrateMode"] in ("CBR", None)


def test_lossy_to_lossy_warns(sample, tmp_path, jpeg_bytes):
    _, plan, _ = _run(sample("mp3"), "aac", tmp_path, jpeg_bytes)
    assert "lossy-to-lossy" in plan.warnings and not plan.bit_perfect


def test_lossy_to_lossless_is_24bit(sample, tmp_path, jpeg_bytes):
    _, plan, res = _run(sample("mp3"), "flac", tmp_path, jpeg_bytes)
    assert "lossy-to-lossless" in plan.warnings
    assert _bits(_probe(res["path"])) == 24


def _packet_sizes(path):
    r = ffmpeg.run([ffmpeg.ffprobe_path(), "-v", "error", "-select_streams", "a:0", "-show_entries",
                    "packet=size", "-of", "json", path])
    return [int(p["size"]) for p in json.loads(r.stdout)["packets"]]


def test_adts_to_m4a_is_remux_without_reencoding(sample, tmp_path, jpeg_bytes):
    src_path = sample("adts")
    _, plan, res = _run(src_path, "aac", tmp_path, jpeg_bytes)
    assert plan.mode == "remux" and plan.bit_perfect and not plan.warnings
    a, b = _packet_sizes(src_path), _packet_sizes(res["path"])
    assert len(a) == len(b)
    assert all(x - y in (7, 9) for x, y in zip(a, b))  # only the ADTS header was stripped


def test_same_format_copies_file_and_never_overwrites_source(sample, tmp_path, jpeg_bytes):
    src_path = sample("flac16")
    before = ffmpeg.audio_packet_md5(src_path)
    loaded = audiofile.load(src_path)
    src = convert.analyze_source(src_path, loaded.info)
    opts = convert.ConvertOptions(target="flac", overwrite="overwrite")  # same folder!
    plan = convert.make_plan(src, opts)
    assert plan.mode == "copy-file"
    out, action = convert.output_path(src_path, opts)
    assert out != src_path and action == "new" and out.endswith("(1).flac")
    res = convert.convert(src, plan, out, _tags(jpeg_bytes), opts)
    convert.release_name(out)
    assert res["verified"]
    assert ffmpeg.audio_packet_md5(src_path) == before == ffmpeg.audio_packet_md5(out)
    assert audiofile.load(src_path).snapshot.fields["title"] == ""   # source untouched


def test_output_policies(tmp_path):
    src = tmp_path / "a.wav"
    src.write_bytes(b"x")
    (tmp_path / "out").mkdir()
    existing = tmp_path / "out" / "a.flac"
    existing.write_bytes(b"y")
    for policy, expect_action, expect_name in (("rename", "new", "a (1).flac"),
                                               ("skip", "skip", "a.flac"),
                                               ("overwrite", "overwrite", "a.flac")):
        opts = convert.ConvertOptions(target="flac", out_dir=str(tmp_path / "out"), overwrite=policy)
        p, action = convert.output_path(str(src), opts)
        assert action == expect_action and os.path.basename(p) == expect_name
        convert.release_name(p)


def test_custom_fields_invalid_for_target_are_dropped(sample, tmp_path, jpeg_bytes):
    src_path = sample("mp3")
    loaded = audiofile.load(src_path)
    src = convert.analyze_source(src_path, loaded.info)
    opts = convert.ConvertOptions(target="flac", out_dir=str(tmp_path / "o"))
    plan = convert.make_plan(src, opts)
    out, _ = convert.output_path(src_path, opts)
    tags = TagChanges(fields={"title": "t"}, custom=[["کلید", "v"], ["GOOD", "1"]], pictures=[])
    res = convert.convert(src, plan, out, tags, opts)
    convert.release_name(out)
    assert any(w.startswith("custom-dropped:") for w in res["warnings"])
    assert ["GOOD", "1"] in audiofile.load(out).snapshot.custom

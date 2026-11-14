import os
import stat

import pytest
from conftest import SAMPLES, TAGGABLE

from tagwave.core import audiofile, ffmpeg
from tagwave.core.errors import FileChangedError, FileReadOnlyError
from tagwave.core.tags import FIELD_KEYS, Picture, SaveOptions, TagChanges, TagError

FULL = {
    "title": "آهنگ تست — Test Song",
    "artist": "هنرمند",
    "album": "آلبوم اول",
    "albumartist": "Various Artists",
    "date": "2024-05-31",
    "genre": "Persian Pop",
    "track": "3",
    "tracktotal": "12",
    "disc": "1",
    "disctotal": "2",
    "composer": "آهنگساز",
    "lyricist": "ترانه‌سرا",
    "conductor": "Conductor X",
    "comment": "یک توضیح\nخط دوم",
    "lyrics": "[00:01.00]خط اول\n[00:02.50]Second line",
    "bpm": "128",
    "publisher": "Label Records",
    "copyright": "© 2024 Someone",
    "encodedby": "Tagwave",
    "isrc": "USRC17607839",
    "grouping": "Group A",
    "compilation": "1",
}


def _pcm(path):
    return ffmpeg.pcm_md5(path)


@pytest.mark.parametrize("name", TAGGABLE)
def test_full_roundtrip(sample, name, jpeg_bytes, png_bytes):
    path = sample(name)
    before_packets = ffmpeg.audio_packet_md5(path)
    before_pcm = _pcm(path)
    loaded = audiofile.load(path)
    assert loaded.can_tag

    pics = [Picture(3, "image/jpeg", "front", jpeg_bytes), Picture(4, "image/png", "back", png_bytes)]
    changes = TagChanges(fields=dict(FULL), custom=[["MY FIELD", "سفارشی"], ["CATALOG", "XYZ-1"]],
                         pictures=pics)
    audiofile.save(path, changes, SaveOptions(), expected=loaded.stamp)

    again = audiofile.load(path)
    for k in FIELD_KEYS:
        assert again.snapshot.fields[k] == FULL[k], (name, k, again.snapshot.fields[k])
    custom = {k.upper(): v for k, v in again.snapshot.custom}
    assert custom.get("MY FIELD") == "سفارشی", again.snapshot.custom
    assert custom.get("CATALOG") == "XYZ-1"
    datas = [p.data for p in again.snapshot.pictures]
    assert datas == [jpeg_bytes, png_bytes], name  # byte-for-byte, front first
    if again.picture_types:
        assert [p.type for p in again.snapshot.pictures] == [3, 4]

    # The audio itself must be untouched.
    assert ffmpeg.audio_packet_md5(path) == before_packets
    assert _pcm(path) == before_pcm


@pytest.mark.parametrize("name", TAGGABLE)
def test_clear_everything(sample, name, jpeg_bytes):
    path = sample(name)
    audiofile.save(path, TagChanges(fields=dict(FULL), pictures=[Picture(3, "image/jpeg", "", jpeg_bytes)],
                                    custom=[["X1", "a"]]), SaveOptions())
    audiofile.save(path, TagChanges(fields={k: "" for k in FIELD_KEYS}, pictures=[], custom=[]),
                   SaveOptions())
    snap = audiofile.load(path).snapshot
    assert all(v == "" for v in snap.fields.values()), snap.fields
    assert snap.pictures == []
    assert [c for c in snap.custom if c[0].upper() == "X1"] == []


@pytest.mark.parametrize("name", ["mp3", "flac16", "aac", "wma", "wavpack"])
def test_partial_track_update_keeps_number(sample, name):
    path = sample(name)
    audiofile.save(path, TagChanges(fields={"track": "5", "tracktotal": "10", "title": "A"}), SaveOptions())
    audiofile.save(path, TagChanges(fields={"tracktotal": "11"}), SaveOptions())
    f = audiofile.load(path).snapshot.fields
    assert (f["track"], f["tracktotal"], f["title"]) == ("5", "11", "A")


def test_untouched_fields_survive(sample):
    path = sample("flac16")
    audiofile.save(path, TagChanges(fields={"title": "One", "artist": "Two"},
                                    custom=[["REPLAYGAIN_TRACK_GAIN", "-6.5 dB"]]), SaveOptions())
    audiofile.save(path, TagChanges(fields={"title": "Uno"}), SaveOptions())
    snap = audiofile.load(path).snapshot
    assert snap.fields["artist"] == "Two"
    assert ["REPLAYGAIN_TRACK_GAIN", "-6.5 dB"] in snap.custom


def test_id3_version_handling(sample):
    from mutagen.id3 import ID3
    path = sample("mp3")
    assert ID3(path).version == (2, 4, 0)  # ffmpeg writes v2.4 ...
    audiofile.save(path, TagChanges(fields={"title": "t"}), SaveOptions())
    assert ID3(path).version == (2, 4, 0)  # ... and "keep" keeps it
    ID3(path).delete()
    audiofile.save(path, TagChanges(fields={"title": "سلام", "date": "2020"}), SaveOptions())
    assert ID3(path).version == (2, 3, 0)  # brand-new tags default to v2.3 (best compatibility)
    audiofile.save(path, TagChanges(fields={"album": "x"}), SaveOptions(id3_version="4"))
    assert ID3(path).version == (2, 4, 0)
    audiofile.save(path, TagChanges(fields={"album": "y"}), SaveOptions())  # keep
    assert ID3(path).version == (2, 4, 0)
    audiofile.save(path, TagChanges(fields={"album": "z"}), SaveOptions(id3_version="3"))
    tags = ID3(path)
    assert tags.version == (2, 3, 0)
    f = audiofile.load(path).snapshot.fields
    assert (f["title"], f["date"], f["album"]) == ("سلام", "2020", "z")


def test_id3_synced_lyrics_written_as_sylt(sample):
    from mutagen.id3 import ID3
    path = sample("mp3")
    lrc = "[00:01.00]one\n[00:02.00]two"
    audiofile.save(path, TagChanges(fields={"lyrics": lrc}), SaveOptions())
    tags = ID3(path)
    assert tags.getall("SYLT")[0].text == [("one", 1000), ("two", 2000)]
    assert audiofile.load(path).snapshot.fields["lyrics"] == lrc
    audiofile.save(path, TagChanges(fields={"lyrics": "plain text"}), SaveOptions())
    assert ID3(path).getall("SYLT") == []


def test_validation_errors(sample):
    path = sample("flac16")
    for bad in ({"date": "last year"}, {"track": "three"}, {"bpm": "fast"}):
        with pytest.raises(TagError):
            audiofile.save(path, TagChanges(fields=bad), SaveOptions())


def test_detects_external_modification(sample):
    path = sample("mp3")
    loaded = audiofile.load(path)
    with open(path, "ab") as f:
        f.write(b"\0")
    with pytest.raises(FileChangedError):
        audiofile.save(path, TagChanges(fields={"title": "x"}), SaveOptions(), expected=loaded.stamp)


def test_read_only_file_is_refused(sample):
    path = sample("mp3")
    os.chmod(path, stat.S_IREAD)
    try:
        with pytest.raises(FileReadOnlyError):
            audiofile.save(path, TagChanges(fields={"title": "x"}), SaveOptions())
    finally:
        os.chmod(path, stat.S_IREAD | stat.S_IWRITE)


def test_no_temp_files_left(sample):
    path = sample("aac")
    audiofile.save(path, TagChanges(fields={"title": "x"}), SaveOptions())
    leftovers = [n for n in os.listdir(os.path.dirname(path)) if ".tagwave-" in n]
    assert leftovers == []


def test_adts_is_read_only_format(sample):
    loaded = audiofile.load(sample("adts"))
    assert not loaded.can_tag
    assert loaded.info["codec"] == "AAC"


@pytest.mark.parametrize("name,codec,lossless,bits", [
    ("mp3", "MP3", False, None), ("flac24", "FLAC", True, 24), ("aac", "AAC", False, None),
    ("alac", "ALAC", True, 16), ("wavf32", "PCM (float)", True, 32), ("wav24", "PCM", True, 24),
    ("opus", "Opus", False, None), ("wma", "WMA", False, None), ("wavpack", "WavPack", True, None),
])
def test_describe(sample, name, codec, lossless, bits):
    info = audiofile.load(sample(name)).info
    assert info["codec"] == codec
    assert info["lossless"] is lossless
    if bits:
        assert info["bitsPerSample"] == bits
    assert 2.5 < info["duration"] < 3.5
    assert info["channels"] == 2

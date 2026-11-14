import os

import pytest

from tagwave.core import rename

F = {"title": "Song: Part 1/2", "artist": "AC/DC", "album": "Live", "date": "1991-05-01", "track": "3",
     "tracktotal": "12", "disc": "1"}


def test_format_name_basic():
    assert rename.format_name("{track} - {artist} - {title}", F, "x") == "03 - AC-DC - Song_ Part 1-2"
    assert rename.format_name("{artist} ({year})", F, "x") == "AC-DC (1991)"
    assert rename.format_name("{disc}-{track:3} {title}", F, "x") == "1-003 Song_ Part 1-2"
    assert rename.format_name("{filename} [{album}]", F, "old") == "old [Live]"


def test_empty_fields_drop_their_separators_only():
    f = {"title": "Wait... -- Remix", "artist": "", "track": ""}
    assert rename.format_name("{track} - {artist} - {title}", f, "x") == "Wait... -- Remix"
    assert rename.format_name("{title} ({artist})", f, "x") == "Wait... -- Remix"
    assert rename.format_name("{artist} - {title}", {"title": "T", "artist": "A"}, "x") == "A - T"


def test_sanitize_reserved_and_trailing():
    assert rename.sanitize("CON") == "_CON"
    assert rename.sanitize("name. ") == "name"
    assert rename.sanitize('a<b>c:"d"') == "a_b_c__d_"


def test_bad_pattern():
    with pytest.raises(rename.PatternError):
        rename.format_name("{nope}", F, "x")
    with pytest.raises(rename.PatternError):
        rename.format_name("plain", F, "x")


def test_preview_and_apply_with_swap(tmp_path):
    a, b = tmp_path / "a.mp3", tmp_path / "b.mp3"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    items = [{"id": "1", "path": str(a), "fields": {"title": "b"}},
             {"id": "2", "path": str(b), "fields": {"title": "a"}}]
    plan = rename.preview(items, "{title}")
    assert [p["status"] for p in plan] == ["ok", "ok"]   # targets exist, but they swap
    res = rename.apply(plan)
    assert all(r["ok"] for r in res)
    assert a.read_bytes() == b"B" and b.read_bytes() == b"A"


def test_preview_existing_target(tmp_path):
    a, other = tmp_path / "a.mp3", tmp_path / "Taken.mp3"
    a.write_bytes(b"A")
    other.write_bytes(b"O")
    plan = rename.preview([{"id": "1", "path": str(a), "fields": {"title": "Taken"}}], "{title}")
    assert plan[0]["status"] == "exists"
    assert rename.apply(plan)[0]["ok"] is False and other.read_bytes() == b"O"


def test_preview_conflicts(tmp_path):
    paths = []
    for n in ("x", "y"):
        p = tmp_path / (n + ".flac")
        p.write_bytes(b"")
        paths.append(str(p))
    plan = rename.preview([{"id": str(i), "path": p, "fields": {"title": "Same"}} for i, p in enumerate(paths)],
                          "{title}")
    assert [p["status"] for p in plan] == ["conflict", "conflict"]
    assert rename.apply(plan)[0]["ok"] is False
    assert sorted(os.listdir(tmp_path)) == ["x.flac", "y.flac"]


def test_parse_filename():
    assert rename.parse_filename("{track} - {artist} - {title}", "03 - Pink Floyd - Time - Live") == \
        {"track": "3", "artist": "Pink Floyd", "title": "Time - Live"}
    assert rename.parse_filename("{artist} - {title}", "NoSeparator") is None
    assert rename.parse_filename("{skip}_{title}", "abc_Hello") == {"title": "Hello"}

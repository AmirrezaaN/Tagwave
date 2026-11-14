import io

import jpeglib
import numpy as np
import pytest
from conftest import make_jpeg, make_png
from PIL import Image

from tagwave.core import images, lyrics


def _dct(data, tmp_path, name):
    p = tmp_path / name
    p.write_bytes(data)
    im = jpeglib.read_dct(str(p))
    im.load()
    return im


@pytest.mark.parametrize("subsampling,mcu", [(0, (8, 8)), (1, (16, 8)), (2, (16, 16))])
@pytest.mark.parametrize("progressive", [False, True])
def test_lossless_jpeg_crop(tmp_path, subsampling, mcu, progressive):
    data = make_jpeg(997, 803, subsampling=subsampling, progressive=progressive)
    caps = images.crop_capabilities(data)
    assert caps["lossless"] and caps["mcu"] == list(mcu)
    x, y = mcu[0] * 5, mcu[1] * 3
    w, h = 611, 517  # odd sizes: partial edge blocks
    out = images.crop_jpeg_lossless(data, x, y, w, h)
    assert Image.open(io.BytesIO(out)).size == (w, h)
    # Every DCT coefficient of the kept area is identical (no requantisation at all).
    a, b = _dct(data, tmp_path, "a.jpg"), _dct(out, tmp_path, "b.jpg")
    vmax = max(s[0] for s in a.samp_factor)
    hmax = max(s[1] for s in a.samp_factor)
    for c, name in enumerate(["Y", "Cb", "Cr"]):
        v, hh = a.samp_factor[c]
        ob = getattr(b, name)
        oy, ox = y * v // vmax // 8, x * hh // hmax // 8
        assert np.array_equal(getattr(a, name)[oy:oy + ob.shape[0], ox:ox + ob.shape[1]], ob)
    assert np.array_equal(a.qt, b.qt)
    # ICC colour profile is preserved
    assert Image.open(io.BytesIO(out)).info.get("icc_profile") == Image.open(io.BytesIO(data)).info.get("icc_profile")


def test_lossless_crop_rejects_misaligned_origin():
    data = make_jpeg(400, 400)
    with pytest.raises(images.ImageError):
        images.crop_jpeg_lossless(data, 3, 0, 100, 100)
    with pytest.raises(images.ImageError):
        images.crop_jpeg_lossless(data, 0, 0, 500, 100)


def test_png_crop_is_pixel_exact():
    data = make_png(300, 200)
    out = images.crop_to_png(data, 10, 20, 150, 100)
    a = np.asarray(Image.open(io.BytesIO(data)))[20:120, 10:160]
    b = np.asarray(Image.open(io.BytesIO(out)))
    assert np.array_equal(a, b)


def test_free_crop_of_jpeg_gives_png():
    data = make_jpeg(300, 300)
    out = images.crop_to_png(data, 1, 1, 50, 60)
    assert images.sniff_mime(out) == images.PNG
    src = np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))[1:61, 1:51]
    assert np.array_equal(src, np.asarray(Image.open(io.BytesIO(out)).convert("RGB")))


def test_prepare_for_embedding():
    jpg, png = make_jpeg(), make_png()
    assert images.prepare_for_embedding(jpg) == (jpg, images.JPEG, False)
    assert images.prepare_for_embedding(png) == (png, images.PNG, False)
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (1, 2, 3)).save(buf, "WEBP", lossless=True)
    out, mime, converted = images.prepare_for_embedding(buf.getvalue())
    assert converted and mime == images.PNG
    assert np.array_equal(np.asarray(Image.open(io.BytesIO(out)).convert("RGB")),
                          np.full((30, 40, 3), (1, 2, 3), np.uint8))


def test_image_meta_and_thumbnail():
    data = make_jpeg(640, 480)
    m = images.image_meta(data)
    assert (m.mime, m.width, m.height, m.depth) == ("image/jpeg", 640, 480, 24)
    th, mime = images.thumbnail(data, 96)
    assert mime == images.JPEG and max(Image.open(io.BytesIO(th)).size) == 96


def test_detect_borders():
    im = Image.new("RGB", (500, 400), (0, 0, 0))
    inner = Image.open(io.BytesIO(make_png(300, 200, alpha=False))).convert("RGB")
    im.paste(inner, (120, 90))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    assert images.detect_borders(buf.getvalue()) == {"x": 120, "y": 90, "w": 300, "h": 200}
    jpg = io.BytesIO()
    im.save(jpg, "JPEG", quality=85)
    r = images.detect_borders(jpg.getvalue())
    assert abs(r["x"] - 120) <= 2 and abs(r["y"] - 90) <= 2 and abs(r["w"] - 300) <= 4 and abs(r["h"] - 200) <= 4


def test_lrc_roundtrip():
    text = "[ar:Someone]\n[00:01.50]first\n[00:03.20][00:10.00]chorus\n[offset:500]\nplain"
    entries, meta = lyrics.parse_lrc(text)
    assert meta["ar"] == "Someone"
    assert entries == [(1000, "first"), (2700, "chorus"), (9500, "chorus")]
    assert lyrics.is_synced(text) and not lyrics.is_synced("just words\nmore words")
    assert lyrics.format_lrc([(61230, "x")]) == "[01:01.23]x"

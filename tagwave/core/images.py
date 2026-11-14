"""Cover-art helpers.

Rule: embedded images are stored byte-for-byte as provided. Pixels are only
touched when the user explicitly crops, and even then the default crop path for
JPEG is a *lossless* DCT-domain crop (no decode/re-encode). Non JPEG/PNG inputs
are converted to PNG, which is pixel-exact.
"""

from __future__ import annotations

import io
import math
import os
import shutil
import tempfile
from dataclasses import dataclass

from PIL import Image, ImageOps

JPEG = "image/jpeg"
PNG = "image/png"
EMBEDDABLE = (JPEG, PNG)

_MODE_DEPTH = {"1": 1, "L": 8, "P": 8, "RGB": 24, "RGBA": 32, "CMYK": 32, "YCbCr": 24,
               "LA": 16, "La": 16, "I;16": 16, "I": 32, "F": 32, "RGBX": 32}


class ImageError(ValueError):
    pass


def sniff_mime(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return JPEG
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return PNG
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    if data[4:12] in (b"ftypavif", b"ftypavis"):
        return "image/avif"
    return None


@dataclass
class ImageMeta:
    mime: str
    width: int
    height: int
    depth: int
    colors: int
    orientation: int = 1


def image_meta(data: bytes) -> ImageMeta:
    mime = sniff_mime(data)
    try:
        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
            depth = _MODE_DEPTH.get(im.mode, 24)
            colors = len(im.getpalette() or []) // 3 if im.mode == "P" else 0
            orientation = 1
            if mime == JPEG:
                try:
                    orientation = int(im.getexif().get(0x0112, 1) or 1)
                except Exception:
                    orientation = 1
            if mime is None:
                mime = Image.MIME.get(im.format or "", "application/octet-stream")
    except Exception:
        return ImageMeta(mime or "application/octet-stream", 0, 0, 0, 0)
    return ImageMeta(mime, w, h, depth, colors, orientation)


def is_image(data: bytes) -> bool:
    return image_meta(data).width > 0


def _encode_png(im: Image.Image, icc: bytes | None) -> bytes:
    if im.mode in ("CMYK", "YCbCr", "RGBX"):
        im = im.convert("RGB")
    elif im.mode not in ("1", "L", "LA", "P", "RGB", "RGBA", "I;16", "I"):
        im = im.convert("RGBA" if "A" in im.mode else "RGB")
    out = io.BytesIO()
    params = {"compress_level": 9}
    if icc:
        params["icc_profile"] = icc
    im.save(out, "PNG", **params)
    return out.getvalue()


def prepare_for_embedding(data: bytes) -> tuple[bytes, str, bool]:
    """Return (data, mime, converted). JPEG/PNG pass through untouched."""
    mime = sniff_mime(data)
    if mime in EMBEDDABLE:
        return data, mime, False
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            icc = im.info.get("icc_profile")
            png = _encode_png(im, icc)
    except Exception as exc:  # pragma: no cover - depends on input
        raise ImageError("Unsupported or damaged image file.") from exc
    return png, PNG, True


# --------------------------------------------------------------------------- JPEG structure

@dataclass
class JpegLayout:
    width: int
    height: int
    mcu_w: int
    mcu_h: int
    lossless_crop: bool   # False for arithmetic/lossless-JPEG variants we can't transcode


_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_SUPPORTED_SOF = {0xC0, 0xC1, 0xC2}


def jpeg_layout(data: bytes) -> JpegLayout | None:
    if sniff_mime(data) != JPEG:
        return None
    i, n = 2, len(data)
    while i + 4 <= n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker == 0xFF:
            i += 1
            continue
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        if marker == 0xD9 or marker == 0xDA:
            return None
        seg_len = int.from_bytes(data[i + 2:i + 4], "big")
        if marker in _SOF_MARKERS:
            seg = data[i + 4:i + 2 + seg_len]
            if len(seg) < 6:
                return None
            height = int.from_bytes(seg[1:3], "big")
            width = int.from_bytes(seg[3:5], "big")
            ncomp = seg[5]
            hmax = vmax = 1
            for c in range(ncomp):
                off = 6 + c * 3
                if off + 2 > len(seg):
                    return None
                samp = seg[off + 1]
                hmax = max(hmax, samp >> 4)
                vmax = max(vmax, samp & 0x0F)
            if ncomp == 1:
                hmax = vmax = 1
            return JpegLayout(width, height, 8 * hmax, 8 * vmax, marker in _SUPPORTED_SOF)
        i += 2 + seg_len
    return None


def crop_capabilities(data: bytes) -> dict:
    meta = image_meta(data)
    layout = jpeg_layout(data)
    lossless = False
    reason = None
    mcu = [1, 1]
    if meta.mime == PNG:
        lossless = True
    elif layout is not None:
        mcu = [layout.mcu_w, layout.mcu_h]
        if not layout.lossless_crop:
            reason = "unsupported-jpeg"
        elif meta.orientation not in (0, 1):
            reason = "exif-rotation"
        else:
            lossless = True
    else:
        reason = "format"
    return {
        "mime": meta.mime, "width": meta.width, "height": meta.height,
        "isJpeg": layout is not None, "lossless": lossless, "losslessReason": reason,
        "mcu": mcu,
    }


def _check_rect(w_img: int, h_img: int, x: int, y: int, w: int, h: int) -> None:
    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > w_img or y + h > h_img:
        raise ImageError("The crop area is outside the image.")


def crop_jpeg_lossless(data: bytes, x: int, y: int, w: int, h: int) -> bytes:
    """Crop a JPEG in the DCT domain: no decoding, no requantisation, zero quality loss.

    The top-left corner must sit on an MCU boundary. Right/bottom edges are free.
    """
    import jpeglib  # imported lazily: native library

    layout = jpeg_layout(data)
    if layout is None or not layout.lossless_crop:
        raise ImageError("This JPEG can't be cropped losslessly.")
    _check_rect(layout.width, layout.height, x, y, w, h)
    if x % layout.mcu_w or y % layout.mcu_h:
        raise ImageError("Lossless crop must start on a %dx%d block boundary." % (layout.mcu_w, layout.mcu_h))

    tmpdir = tempfile.mkdtemp(prefix="tagwave-crop-")
    try:
        src = os.path.join(tmpdir, "in.jpg")
        dst = os.path.join(tmpdir, "out.jpg")
        with open(src, "wb") as f:
            f.write(data)
        im = jpeglib.read_dct(src)
        im.load()
        names = ["Y"]
        if im.has_chrominance:
            names += ["Cb", "Cr"]
        if im.has_black:
            names += ["K"]
        samp = [list(map(int, s)) for s in im.samp_factor]   # [v, h] per component
        vmax = max(s[0] for s in samp)
        hmax = max(s[1] for s in samp)
        block_dims = []
        for c, name in enumerate(names):
            v, hh = samp[c]
            bh = math.ceil(math.ceil(h * v / vmax) / 8)
            bw = math.ceil(math.ceil(w * hh / hmax) / 8)
            oy = y * v // vmax // 8
            ox = x * hh // hmax // 8
            arr = getattr(im, name)
            part = arr[oy:oy + bh, ox:ox + bw]
            if part.shape[0] != bh or part.shape[1] != bw:
                raise ImageError("Unexpected JPEG block layout.")
            setattr(im, name, part.copy())
            block_dims.append([bh, bw])
        import numpy as np
        im.height, im.width = h, w
        im.block_dims = np.array(block_dims)
        im.write_dct(dst)
        with open(dst, "rb") as f:
            out = f.read()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
    with Image.open(io.BytesIO(out)) as check:
        if check.size != (w, h):
            raise ImageError("Lossless crop verification failed.")
    return out


def crop_to_png(data: bytes, x: int, y: int, w: int, h: int) -> bytes:
    """Pixel-exact crop saved as PNG (lossless relative to the decoded image)."""
    with Image.open(io.BytesIO(data)) as im:
        icc = im.info.get("icc_profile")
        im = ImageOps.exif_transpose(im)
        im.load()
        _check_rect(im.width, im.height, x, y, w, h)
        return _encode_png(im.crop((x, y, x + w, y + h)), icc)


def detect_borders(data: bytes, tolerance: int = 22) -> dict:
    """Find the content box inside uniform borders (letterboxing, white frames...).

    Coordinates are in the displayed (EXIF-rotated) image space.
    """
    import numpy as np

    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        arr = np.asarray(im, dtype=np.int16)
    h, w = arr.shape[:2]
    corners = np.array([arr[0, 0], arr[0, -1], arr[-1, 0], arr[-1, -1]])
    bg = np.median(corners, axis=0)
    diff = np.abs(arr - bg).max(axis=2) > tolerance
    rows = np.nonzero(diff.mean(axis=1) > 0.004)[0]
    cols = np.nonzero(diff.mean(axis=0) > 0.004)[0]
    if not len(rows) or not len(cols):
        return {"x": 0, "y": 0, "w": w, "h": h}
    return {"x": int(cols[0]), "y": int(rows[0]), "w": int(cols[-1] - cols[0] + 1), "h": int(rows[-1] - rows[0] + 1)}


def thumbnail(data: bytes, size: int) -> tuple[bytes, str]:
    """Small preview for the UI only (never embedded in files)."""
    size = max(16, min(int(size), 1024))
    with Image.open(io.BytesIO(data)) as im:
        im = ImageOps.exif_transpose(im)
        im.draft("RGB", (size * 2, size * 2))
        has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        im.thumbnail((size, size), Image.LANCZOS)
        out = io.BytesIO()
        if has_alpha:
            im.save(out, "PNG")
            return out.getvalue(), PNG
        im.save(out, "JPEG", quality=90)
        return out.getvalue(), JPEG

"""Render the Tagwave logo to assets/tagwave.ico (+ PNGs) with supersampling."""

import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets")
STOPS = [(0.0, (139, 92, 246)), (0.55, (99, 102, 241)), (1.0, (34, 211, 238))]


def _lerp(a, b, t):
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


def _grad(t):
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            return _lerp(c0, c1, (t - t0) / (t1 - t0))
    return STOPS[-1][1]


def render(size: int) -> Image.Image:
    s = 8
    n = size * s
    base = Image.new("RGBA", (n, n))
    px = base.load()
    for y in range(n):
        for x in range(n):
            t = min(1.0, max(0.0, (x * 52 + y * 56) / (n * 108) * 1.0))
            r, g, b = _grad(t)
            px[x, y] = (r, g, b, 255)
    mask = Image.new("L", (n, n), 0)
    pad = n * 2 // 64
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, n - pad, n - pad], radius=n * 16 // 64, fill=255)
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    img.paste(base, (0, 0), mask)
    d = ImageDraw.Draw(img)
    bars = [(13, 27, 10), (21, 19, 26), (29, 13, 38), (37, 21, 22), (45, 25, 14)]
    for x, y, h in bars:
        u = n / 64
        d.rounded_rectangle([x * u, y * u, (x + 5) * u, (y + h) * u], radius=2.5 * u, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(OUT, exist_ok=True)
    big = render(256)
    big.save(os.path.join(OUT, "tagwave.png"))
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    frames = [render(sz) for sz in sizes]
    frames[-1].save(os.path.join(OUT, "tagwave.ico"), format="ICO", sizes=[(sz, sz) for sz in sizes],
                    append_images=frames[:-1])
    # Inno Setup wizard images (55x55 small, 164x314 large) as BMP.
    small = Image.new("RGB", (110, 110), (255, 255, 255))
    small.paste(render(96), (7, 7), render(96))
    small.save(os.path.join(OUT, "wizard-small.bmp"))
    large = Image.new("RGB", (328, 628))
    lp = large.load()
    for y in range(628):
        for x in range(328):
            lp[x, y] = _grad(min(1.0, (x * 0.4 + y) / 760))
    logo = render(160)
    large.paste(logo, (84, 200), logo)
    large.save(os.path.join(OUT, "wizard-large.bmp"))
    print("icons written to", OUT)


if __name__ == "__main__":
    main()

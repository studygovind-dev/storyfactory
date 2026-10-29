#!/usr/bin/env python3
"""Draws the StoryBite TV profile picture and banners (needs: pip install pillow).
   py assets/brand/make_brand.py  ->  profile.png, youtube_banner.png, facebook_cover.png"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).resolve().parent
FONT = "C:/Windows/Fonts/seguibl.ttf"   # Segoe UI Black
TOP, BOTTOM = (88, 28, 135), (236, 72, 103)   # purple -> coral
YELLOW, WHITE = (255, 214, 10), (255, 255, 255)


def gradient(w, h):
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))
    return img


def icon(d, cx, cy, s):
    """White speech bubble with a coral play button: 'stories you watch'."""
    r = s // 2
    d.rounded_rectangle([cx - r, cy - r * 0.75, cx + r, cy + r * 0.6], radius=r * 0.35, fill=WHITE)
    d.polygon([(cx - r * 0.45, cy + r * 0.55), (cx - r * 0.1, cy + r * 0.55), (cx - r * 0.55, cy + r * 0.95)],
              fill=WHITE)
    t = r * 0.38
    d.polygon([(cx - t * 0.7, cy - t - r * 0.07), (cx - t * 0.7, cy + t - r * 0.07), (cx + t, cy - r * 0.07)],
              fill=BOTTOM)


def wordmark(d, cx, y, size, tagline=None):
    f = ImageFont.truetype(FONT, size)
    tv = ImageFont.truetype(FONT, int(size * 0.62))
    word, w1 = "StoryBite", d.textlength("StoryBite", font=f)
    w2 = d.textlength("TV", font=tv) + size * 0.4
    x = cx - (w1 + size * 0.2 + w2) / 2
    d.text((x, y), word, font=f, fill=WHITE)
    px = x + w1 + size * 0.2
    py = y + size * 0.28
    d.rounded_rectangle([px, py, px + w2, py + size * 0.8], radius=size * 0.18, fill=YELLOW)
    d.text((px + size * 0.2, py + size * 0.0), "TV", font=tv, fill=TOP)
    if tagline:
        tf = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", int(size * 0.32))
        d.text((cx, y + size * 1.45), tagline, font=tf, fill=WHITE, anchor="mm")


def shadowed(img, draw_fn):
    """Soft drop shadow under everything draw_fn paints."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(layer))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), mask=layer.split()[3])
    shadow = shadow.filter(ImageFilter.GaussianBlur(img.size[1] // 90))
    base = img.convert("RGBA")
    base.alpha_composite(shadow, (0, img.size[1] // 160))
    base.alpha_composite(layer)
    return base.convert("RGB")


def profile():
    s = 1080
    img = gradient(s, s)
    img = shadowed(img, lambda d: (icon(d, s // 2, int(s * 0.40), int(s * 0.46)),
                                   wordmark(d, s // 2, int(s * 0.63), 120)))
    img.save(OUT / "profile.png")


def banner(w, h, name, size, tagline):
    img = gradient(w, h)
    cx, cy = w // 2, h // 2
    img = shadowed(img, lambda d: (icon(d, cx - int(size * 3.9), cy, int(size * 1.5)),
                                   wordmark(d, cx + int(size * 0.9), cy - int(size * 0.75), size, tagline)))
    img.save(OUT / name)


if __name__ == "__main__":
    profile()
    # YouTube shows only the middle 1546x423 on every device; keep everything there.
    banner(2560, 1440, "youtube_banner.png", 150, "New stories every day  •  9 AM · 1 PM · 5 PM")
    banner(1640, 624, "facebook_cover.png", 120, "New stories every day  •  9 AM · 1 PM · 5 PM")
    print("Saved in", OUT)

"""Render the iris as a blind emboss, like the one in the home project: the
paper's own colour, raised, with a crisp light edge along the upper left and a
soft shade along the lower right. Done as an image (not CSS filters) so it looks
the same in every browser.

    python3 scripts/emboss_iris.py   # writes digest/static/iris-emboss.png
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

SRC = Path(__file__).resolve().parent.parent / "digest/static/iris-white.png"
OUT = SRC.with_name("iris-emboss.png")
PAPER = (241, 233, 216)   # the welcome sheet (warmer, like the home project)
SCALE = 2                 # rendered at 2x the source
K = 6.3                   # rendered pixels per CSS pixel at the size shown (~84px)
PAD = 48


def main():
    src = Image.open(SRC).convert("RGBA")
    a = src.getchannel("A").resize((src.width * SCALE, src.height * SCALE), Image.LANCZOS)
    canvas = Image.new("L", (a.width + 2 * PAD, a.height + 2 * PAD), 0)
    canvas.paste(a, (PAD, PAD))
    a = canvas
    off = lambda img, dx, dy: ImageChops.offset(img, round(dx), round(dy))
    alpha = lambda img, k: img.point(lambda v: min(255, int(v * k)))

    def layer(rgb, mask):
        l = Image.new("RGBA", a.size, (*rgb, 0))
        l.putalpha(mask)
        return l

    out = Image.new("RGBA", a.size, (0, 0, 0, 0))
    # 1. a soft lift: the whole shape's shadow, a little down and to the right
    lift = off(a, 1.2 * K, 1.8 * K).filter(ImageFilter.GaussianBlur(2.2 * K))
    out = Image.alpha_composite(out, layer((80, 60, 30), alpha(lift, 0.16)))
    # 2. the contact shade hugging the lower-right edges
    contact = off(a, 0.9 * K, 0.9 * K).filter(ImageFilter.GaussianBlur(0.7 * K))
    out = Image.alpha_composite(out, layer((80, 60, 30), alpha(contact, 0.30)))
    # 3. the light catching the upper-left edges, just outside the shape
    rim = off(a, -0.6 * K, -0.6 * K).filter(ImageFilter.GaussianBlur(0.25 * K))
    out = Image.alpha_composite(out, layer((255, 255, 255), alpha(rim, 0.95)))
    # 4. the shape itself, in the paper's colour, on top
    out = Image.alpha_composite(out, layer(PAPER, a))
    out = out.crop(out.getbbox())
    out.save(OUT, optimize=True)
    print(f"wrote {OUT} {out.size}")


if __name__ == "__main__":
    main()

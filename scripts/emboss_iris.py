"""Render the iris as a blind deboss: the paper's own colour, pressed in, with a
shade along the upper-left inside edges and light along the lower-right. Done as
an image (not CSS filters) so it looks the same in every browser.

    python3 scripts/emboss_iris.py   # writes digest/static/iris-deboss.png
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

SRC = Path(__file__).resolve().parent.parent / "digest/static/iris-white.png"
OUT = SRC.with_name("iris-deboss.png")
SCALE = 2          # render larger than the source, for crisp edges on phones
DEPTH = 8          # how far the edge reaches, in rendered pixels
PAD = 8


def main():
    src = Image.open(SRC).convert("RGBA")
    a = src.getchannel("A").resize((src.width * SCALE, src.height * SCALE), Image.LANCZOS)
    w, h = a.size
    canvas = Image.new("L", (w + 2 * PAD, h + 2 * PAD), 0)
    canvas.paste(a, (PAD, PAD))
    a = canvas

    def shift(img, dx, dy):
        return ImageChops.offset(img, dx, dy)

    # inside the shape, where the neighbour up-left is outside: the shaded wall
    shade = ImageChops.subtract(a, shift(a, DEPTH, DEPTH)).filter(ImageFilter.GaussianBlur(2.0))
    # inside the shape, where the neighbour down-right is outside: the lit wall
    light = ImageChops.subtract(a, shift(a, -DEPTH, -DEPTH)).filter(ImageFilter.GaussianBlur(2.0))

    out = Image.new("RGBA", a.size, (0, 0, 0, 0))
    # the pressed floor: a whisper darker than the paper
    floor = Image.new("RGBA", a.size, (110, 92, 60, 0))
    floor.putalpha(a.point(lambda v: v * 14 // 255))
    out = Image.alpha_composite(out, floor)
    dark = Image.new("RGBA", a.size, (90, 72, 45, 0))
    dark.putalpha(shade.point(lambda v: min(255, v * 120 // 255)))
    out = Image.alpha_composite(out, dark)
    lit = Image.new("RGBA", a.size, (255, 255, 255, 0))
    lit.putalpha(light.point(lambda v: min(255, v * 235 // 255)))
    out = Image.alpha_composite(out, lit)
    out.save(OUT, optimize=True)
    print(f"wrote {OUT} {out.size}")


if __name__ == "__main__":
    main()

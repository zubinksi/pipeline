"""Site icons from the iris: the cream iris on the site's navy ground.

    python3 scripts/make_icons.py   # writes digest/static/icon-*.png
"""
from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parent.parent / "digest/static"
NAVY = (23, 39, 64, 255)       # --ground
CREAM = (241, 233, 216, 255)   # the paper


def icon(size: int, pad: float, radius: float) -> Image.Image:
    src = Image.open(STATIC / "iris-white.png").convert("RGBA")
    big = size * 4
    canvas = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    # rounded navy tile
    from PIL import ImageDraw
    ImageDraw.Draw(canvas).rounded_rectangle([0, 0, big - 1, big - 1], radius=int(big * radius), fill=NAVY)
    inner = int(big * (1 - 2 * pad))
    scale = inner / max(src.size)
    iris_mask = src.getchannel("A").resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
    iris = Image.new("RGBA", iris_mask.size, CREAM)
    iris.putalpha(iris_mask)
    canvas.alpha_composite(iris, ((big - iris.width) // 2, (big - iris.height) // 2 + int(big * 0.01)))
    return canvas.resize((size, size), Image.LANCZOS)


def main():
    icon(32, 0.14, 0.18).save(STATIC / "icon-32.png", optimize=True)
    icon(192, 0.16, 0.18).save(STATIC / "icon-192.png", optimize=True)
    # iOS rounds the corners itself: a full-bleed square
    icon(180, 0.17, 0.0).save(STATIC / "icon-180.png", optimize=True)
    print("wrote icons")


if __name__ == "__main__":
    main()

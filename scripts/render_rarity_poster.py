"""Compose the GitHub poster from the actual animation frames."""

import json
import os
from pathlib import Path
import random

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PET = ROOT / "pets" / "clodex"
DATA = json.loads((PET / "pet.json").read_text(encoding="utf-8"))
FONTS = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
WIDTH, HEIGHT = 1440, 1424
INK = "#f7edd9"
MUTED = "#b9a99c"


def font(size, name="bahnschrift.ttf"):
    return ImageFont.truetype(str(FONTS / name), size)


def frame(clip, progress):
    index = round((DATA["clips"][clip]["frames"] - 1) * progress)
    x, y = index % 8 * 192, index // 8 * 208
    with Image.open(PET / "clips" / (clip + ".webp")) as atlas:
        tile = atlas.crop((x, y, x + 192, y + 208)).convert("RGBA")
    return tile.crop(tile.getbbox())


def pixel_art(canvas, clip, progress, center, maximum):
    tile = frame(clip, progress)
    factor = min(maximum[0] / tile.width, maximum[1] / tile.height)
    tile = tile.resize((round(tile.width * factor), round(tile.height * factor)), Image.Resampling.NEAREST)
    where = (center[0] - tile.width // 2, center[1] - tile.height // 2)
    canvas.alpha_composite(tile, where)


def panel(canvas, bounds, fill, outline):
    x, y, right, bottom = bounds
    drawing = ImageDraw.Draw(canvas)
    drawing.rounded_rectangle((x, y + 8, right, bottom + 8), radius=23, fill="#1b1113")
    drawing.rounded_rectangle(bounds, radius=23, fill=fill, outline=outline, width=2)


def label(draw, xy, text, size, fill=INK, anchor="mm"):
    draw.text(xy, text, font=font(size), fill=fill, anchor=anchor)


def tier_row(canvas, y, entries, width, color, border):
    gap = 16
    left = (WIDTH - (len(entries) * width + (len(entries) - 1) * gap)) // 2
    for index, (clip, progress) in enumerate(entries):
        x = left + index * (width + gap)
        panel(canvas, (x, y, x + width, y + 198), color, border)
        draw = ImageDraw.Draw(canvas)
        draw.ellipse((x + width // 2 - 50, y + 167, x + width // 2 + 50, y + 175), fill="#241b21")
        pixel_art(canvas, clip, progress, (x + width // 2, y + 97), (width - 46, 137))


def main():
    canvas = Image.new("RGBA", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(canvas)
    for y in range(HEIGHT):
        progress = y / HEIGHT
        draw.line((0, y, WIDTH, y), fill=(round(47 - 23 * progress), round(30 - 11 * progress), 34))
    rng = random.Random(614)
    for _ in range(1250):
        x, y = rng.randrange(WIDTH), rng.randrange(HEIGHT)
        draw.point((x, y), fill="#6c4740" if rng.randrange(5) == 0 else "#4b3233")

    label(draw, (720, 99), "CLODEX", 114)
    draw.line((618, 170, 822, 170), fill="#ce8a57", width=2)

    hero = (473, 215, 967, 617)
    panel(canvas, hero, "#efb745", "#ffe0a0")
    draw = ImageDraw.Draw(canvas)
    draw.ellipse((557, 249, 883, 575), fill="#facb61", outline="#fbd681", width=2)
    for x, y in [(552, 308), (865, 295), (875, 450), (555, 485), (823, 538)]:
        draw.line((x - 6, y, x + 6, y), fill="#fff0bc", width=2)
        draw.line((x, y - 6, x, y + 6), fill="#fff0bc", width=2)
    draw.ellipse((629, 534, 811, 552), fill="#d99a34")
    pixel_art(canvas, "6034908291920830143", 0.64, (720, 412), (278, 255))
    draw.rounded_rectangle((647, 565, 793, 601), radius=18, fill="#34211c")
    label(draw, (720, 583), "0.01%", 22, "#ffe8ae")

    groups = {
        weight: [item["clip"] for item in DATA["idleChoices"] if item["weight"] == weight]
        for weight in (1250, 8000)
    }
    label(draw, (720, 662), "0.5%", 33, "#d9b9ff")
    tier_row(canvas, 694, list(zip(groups[1250], (0.58, 0.35, 0.46, 0.33))), 226, "#403047", "#735a7c")
    label(draw, (720, 936), "4%", 33, "#fac1a2")
    tier_row(canvas, 968, list(zip(groups[8000], (0.37, 0.44, 0.59, 0.38, 0.57))), 229, "#543831", "#865f52")

    panel(canvas, (87, 1212, 1353, 1358), "#322823", "#665247")
    draw = ImageDraw.Draw(canvas)
    label(draw, (141, 1285), "95.49%", 41, MUTED, "lm")
    draw.line((360, 1237, 360, 1333), fill="#665247", width=2)
    idle = DATA["states"]["idle"][0]
    for x, progress in zip((555, 801, 1047), (0.00, 0.36, 0.70)):
        pixel_art(canvas, idle, progress, (x, 1285), (119, 84))

    output = ROOT / "docs" / "clodex-rarities.webp"
    output.parent.mkdir(exist_ok=True)
    canvas.convert("RGB").save(output, "WEBP", quality=91, method=6)
    print(output)


if __name__ == "__main__":
    main()

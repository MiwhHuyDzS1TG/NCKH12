from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SLIDES = [
    "s01", "s02", "s03", "s04", "s05", "s06", "s07", "s08", "s09",
    "s10", "s11", "s12", "s13", "s14", "a01", "a02", "a03", "a04",
]


def build_sheet(size: str) -> None:
    source = Path("screenshots") / size
    thumb_width = 480
    thumb_height = 270
    label_height = 34
    columns = 3
    rows = (len(SLIDES) + columns - 1) // columns
    canvas = Image.new("RGB", (columns * thumb_width, rows * (thumb_height + label_height)), "#dbe4ea")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()

    for index, slide in enumerate(SLIDES):
        image = Image.open(source / f"{slide}.png").convert("RGB")
        image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
        x = (index % columns) * thumb_width
        y = (index // columns) * (thumb_height + label_height)
        canvas.paste(image, (x, y))
        draw.rectangle((x, y + thumb_height, x + thumb_width, y + thumb_height + label_height), fill="#07182b")
        draw.text((x + 12, y + thumb_height + 10), slide.upper(), fill="white", font=font)

    canvas.save(Path("screenshots") / f"contact-sheet-{size.split('x')[0]}.png", quality=94)


for viewport in ("1920x1080", "1366x768"):
    build_sheet(viewport)

print("Created contact sheets for 1920 and 1366 screenshots.")

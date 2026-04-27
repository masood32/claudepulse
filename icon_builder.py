"""
Builds the dynamic system tray icon — a colored circle with % text.
"""

from PIL import Image, ImageDraw, ImageFont

GREEN  = (50,  180,  80)
YELLOW = (230, 160,  30)
RED    = (220,  50,  50)
GRAY   = (100, 100, 100)


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _pick_color(pct: int, warn: int, crit: int, error: bool) -> tuple:
    if error:
        return GRAY
    if pct >= crit:
        return RED
    if pct >= warn:
        return YELLOW
    return GREEN


def build_icon(pct: int, warn: int = 70, crit: int = 85, error: bool = False) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    color = _pick_color(pct, warn, crit, error)

    # Circle background
    m = 2
    draw.ellipse([m, m, size - m, size - m], fill=(*color, 230))

    # Subtle inner ring for depth
    inner = 6
    draw.ellipse([inner, inner, size - inner, size - inner],
                 outline=(255, 255, 255, 30), width=1)

    # Text
    text = "?" if error else f"{pct}%"
    font_size = 20 if len(text) <= 3 else 16
    font = _get_font(font_size)

    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1]

    # Shadow
    draw.text((tx + 1, ty + 1), text, font=font, fill=(0, 0, 0, 120))
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 240))

    return img

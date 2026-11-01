from __future__ import annotations

import textwrap
from pathlib import Path

from tools.common import NewsletterError
from tools.research import NewsletterResearch


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size, index=1 if bold and candidate.endswith(".ttc") else 0)
        except OSError:
            continue
    return ImageFont.load_default()


def generate_infographic(research: NewsletterResearch, destination: Path) -> None:
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:
        raise NewsletterError("Pillow mangler. Kør: .venv/bin/python -m pip install -r requirements.txt") from exc
    width, height = 1200, 675
    image = Image.new("RGB", (width, height), "#172033")
    draw = ImageDraw.Draw(image)
    for y in range(height):
        ratio = y / height
        draw.line((0, y, width, y), fill=(23 + int(12 * ratio), 32 + int(18 * ratio), 51 + int(35 * ratio)))
    draw.text((70, 52), "TRE POINTER", font=_font(23, True), fill="#9CBcff")
    subject = "\n".join(textwrap.wrap(research.subject, width=42)[:2])
    draw.multiline_text((70, 92), subject, font=_font(45, True), fill="white", spacing=8)
    colors = ["#7AA2FF", "#7ED6B2", "#FFBC7A"]
    card_y, card_h, gap = 235, 355, 24
    card_w = (width - 140 - gap * 2) // 3
    for index, point in enumerate(research.points):
        x = 70 + index * (card_w + gap)
        draw.rounded_rectangle((x, card_y, x + card_w, card_y + card_h), radius=22, fill="#FFFFFF", outline=colors[index], width=4)
        draw.ellipse((x + 28, card_y + 28, x + 78, card_y + 78), fill=colors[index])
        draw.text((x + 46, card_y + 40), str(index + 1), font=_font(22, True), fill="#172033", anchor="mm")
        heading = "\n".join(textwrap.wrap(point.heading, width=22)[:3])
        draw.multiline_text((x + 28, card_y + 105), heading, font=_font(27, True), fill="#172033", spacing=7)
        body = "\n".join(textwrap.wrap(point.body, width=36)[:7])
        draw.multiline_text((x + 28, card_y + 205), body, font=_font(19), fill="#47536A", spacing=6)
    image.save(destination, format="PNG", optimize=True)

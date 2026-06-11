"""Generator placeholderowej ikony aplikacji ``icon.ico``.

Tworzy prostą ikonę (gradient + litera „ε") na potrzeby buildu, dopóki nie
zostanie dostarczona docelowa grafika. Jeśli w ``src/epubforge/gui/assets/``
istnieje już prawdziwy ``icon.ico``, build używa jego — patrz spec-i.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_SIZES = [256, 128, 64, 48, 32, 16]
_DEFAULT_OUTPUT = Path(__file__).parent / "icon.ico"


def create_icon(output: Path = _DEFAULT_OUTPUT) -> Path:
    """Generuje wielorozmiarową ikonę ``.ico`` i zwraca ścieżkę zapisu."""
    images: list[Image.Image] = []
    for size in _SIZES:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Tło: pionowy gradient ciemnozielony.
        for y in range(size):
            channel = int(29 + (158 - 29) * (y / size))
            draw.line([(0, y), (size, y)], fill=(29, channel, 117, 255))

        # Litera „ε" na środku.
        try:
            font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
                "arial.ttf", int(size * 0.7)
            )
        except OSError:
            font = ImageFont.load_default()

        text = "ε"
        bbox = draw.textbbox((0, 0), text, font=font)
        x = (size - (bbox[2] - bbox[0])) // 2 - bbox[0]
        y = (size - (bbox[3] - bbox[1])) // 2 - bbox[1]
        draw.text((x, y), text, fill=(255, 255, 255, 255), font=font)
        images.append(img)

    images[0].save(
        output,
        format="ICO",
        sizes=[(s, s) for s in _SIZES],
        append_images=images[1:],
    )
    print(f"Utworzono {output}")
    return output


if __name__ == "__main__":
    create_icon()

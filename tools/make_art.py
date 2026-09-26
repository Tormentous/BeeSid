"""Redraw the Bee Sid app art from his picture (rapier/assets/bee_sid.png): the icon (PNG + ICO) and the splash.

Run from the repository root with the desktop extras installed:

    python tools/make_art.py

The splash is a picture of the app's own home banner, so it always matches the app.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "rapier" / "assets"
FULL = (32, 40, 48, 64, 96, 128, 256)
HEAD = (16, 20, 24)  # at these sizes his whole picture is a speck, so use his hat, shades and moustache
HEAD_BOX = (86, 0, 234, 148)


def Sticker(art: Image.Image, size: int) -> Image.Image:
    """`art` at `size` pixels with a white outline, so Bee Sid stands out on dark and light taskbars."""
    edge = max(1, round(size / 64))
    img = art.resize((size, size), Image.LANCZOS)
    ring = img.getchannel("A").point(lambda a: 255 if a > 100 else 0).filter(ImageFilter.MaxFilter(2 * edge + 1))
    if size >= 48:
        ring = ring.filter(ImageFilter.GaussianBlur(0.6))
    out = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    out.putalpha(ring)
    out.alpha_composite(img)
    return out


def Icons() -> None:
    bee = Image.open(ASSETS / "bee_sid.png").convert("RGBA")
    images = {size: Sticker(bee, size) for size in FULL} | {size: Sticker(bee.crop(HEAD_BOX), size) for size in HEAD}
    images[256].save(ASSETS / "icon.png", optimize=True)
    sizes = sorted(images)
    images[256].save(ASSETS / "icon.ico", sizes=[(s, s) for s in sizes],
                     append_images=[images[s] for s in sizes if s != 256])


def Splash() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    sys.path.insert(0, str(ROOT))
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QColor, QPainter, QPen
    from PySide6.QtWidgets import QApplication, QVBoxLayout

    from rapier import desktop as K

    app = QApplication.instance() or QApplication([])
    K.LoadFonts()
    hero = K.Hero(art=200)
    box = QVBoxLayout(hero)
    box.setContentsMargins(18, 34, 150, 26)
    box.addWidget(K.Logo(size=66), 0, Qt.AlignmentFlag.AlignLeft)
    box.addStretch()
    box.addWidget(K.Text("Opening Bee Sid's desk…", 15, True, K.TEXT))
    hero.resize(560, 300)
    hero.show()
    app.processEvents()
    picture = hero.grab()
    frame = QPainter(picture)
    frame.setPen(QPen(QColor(K.BORDER), 2))
    frame.drawRect(picture.rect().adjusted(1, 1, -1, -1))
    frame.end()
    picture.save(str(ASSETS / "splash.png"))


if __name__ == "__main__":
    Icons()
    Splash()
    print("redrew", ", ".join(p.name for p in (ASSETS / "icon.png", ASSETS / "icon.ico", ASSETS / "splash.png")))

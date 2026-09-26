"""Bee Sid: the game-style Windows/Linux app for saved backtests and new backtest runs (it never places orders)."""

from __future__ import annotations

import json
import math
import random
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from functools import cache
from io import StringIO
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QStandardPaths, Qt, QThread, QUrl, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QFontMetrics, QFontMetricsF, QIcon,
                           QImageReader, QLinearGradient, QPainter, QPainterPath, QPalette, QPen, QPixmap,
                           QPolygonF, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .desktop_data import (LATEST, AdoptOldHome, AppPaths, BacktestArgs, DisplayName, EngineCheck, EquityCurve,
                           GoalLabel, GoalScore, LoadReports, Money, NiceStep, Paths, Publish, Report, RunFolder,
                           Staging)

ASSETS = Path(__file__).resolve().parent / "assets"

# LabradorSim's France-desk navy (hue 228) wearing Chipper's game pieces: slanted buttons, starfields, a colour
# per tab and a bouncy logo. Cantarell is coolbrador.com's font, bundled under the SIL Open Font License.
NAVY, NAVY_2, NAVY_3, BORDER, BORDER_HI = "#070d21", "#0e1634", "#18234e", "#273468", "#3a4a8f"
WHITE, TEXT, SOFT, CREAM = "#ffffff", "#e8eefc", "#9aa6c8", "#f5edd8"
GOLD, STAR, SILVER, BRONZE = "#e5c87d", "#ece053", "#c7ced9", "#d08a4a"
BEE_LIGHT, BEE, BEE_DARK, INK = "#ffd95a", "#f0b429", "#daa321", "#15120d"  # BEE_DARK is sampled from his wings
RED, BLUE, PURPLE, GREEN, ORANGE, CYAN = "#da444b", "#1861da", "#7a3cff", "#3cb043", "#ff8a1f", "#2fb4e8"
UP, DOWN = "#34d399", "#f87171"
SLOT_COLORS = (BLUE, PURPLE, RED, GREEN, ORANGE, CYAN)
DARK_INK = {GREEN, ORANGE, CYAN, GOLD, STAR, SILVER, BRONZE, UP}
FAMILIES = ["Cantarell", "Segoe UI", "Noto Sans", "DejaVu Sans"]
RULES = ("<b>PLAN</b> every trade at 1R or better, <b>STAY</b> under the $2,000 drawdown, <b>BE FLAT</b> before "
         "the close, <b>TRADE WITH</b> the bigger trend, <b>WAIT</b> for the pullback into the OTE zone, and "
         "<b>NEVER</b> let the desk place a real order.")
INTRO = ("Name your run to keep it; capitals and spaces are fine. Leave the name blank and it replaces "
         "“Latest Run”. The first run downloads market data from Yahoo, which only keeps recent 1m and 5m history.")

STYLE = f"""
QWidget {{ color: {TEXT}; }}
QFrame#hud {{ background: #0a1130; border-bottom: 1px solid {BORDER}; }}
QFrame#review {{ border-left: 3px solid {BLUE}; }}
QLineEdit, QComboBox {{ background: {NAVY_3}; border: 1px solid {BORDER}; padding: 8px 10px; }}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{ border-color: {GOLD}; }}
QComboBox::drop-down {{ border: 0; width: 30px; }}
QComboBox::down-arrow {{ image: url("{(ASSETS / 'arrow.svg').as_posix()}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {NAVY_3}; border: 1px solid {GOLD}; outline: 0;
                               selection-background-color: {GOLD}; selection-color: {NAVY}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {BORDER}; background: {NAVY_3}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD};
                                image: url("{(ASSETS / 'check.svg').as_posix()}"); }}
QTableWidget {{ background: {NAVY_2}; alternate-background-color: #121c44; border: 0; }}
QTableWidget::item {{ padding: 0 10px; }}
QHeaderView::section {{ background: {NAVY_3}; color: {GOLD}; padding: 8px 10px; border: 0; font-weight: 700; }}
QScrollArea {{ border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {BLUE}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QToolTip {{ background: {NAVY_3}; color: {TEXT}; border: 1px solid {GOLD}; padding: 6px; }}
"""


@cache
def LoadFonts() -> None:
    for path in sorted((ASSETS / "fonts").glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(path))


def Font(size: int, bold: bool = False, spacing: float = 0.0) -> QFont:
    font = QFont()
    font.setFamilies(FAMILIES)
    font.setPixelSize(size)
    font.setBold(bold)
    if spacing:
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return font


def Palette() -> QPalette:
    palette = QPalette()
    roles = {QPalette.ColorRole.Window: NAVY, QPalette.ColorRole.WindowText: TEXT, QPalette.ColorRole.Base: NAVY_3,
             QPalette.ColorRole.AlternateBase: NAVY_2, QPalette.ColorRole.Text: TEXT,
             QPalette.ColorRole.Button: NAVY_3, QPalette.ColorRole.ButtonText: TEXT,
             QPalette.ColorRole.Highlight: GOLD, QPalette.ColorRole.HighlightedText: NAVY,
             QPalette.ColorRole.ToolTipBase: NAVY_3, QPalette.ColorRole.ToolTipText: TEXT,
             QPalette.ColorRole.PlaceholderText: SOFT, QPalette.ColorRole.BrightText: WHITE,
             QPalette.ColorRole.Link: CYAN}
    for role, color in roles.items():
        palette.setColor(role, QColor(color))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        palette.setColor(QPalette.ColorGroup.Disabled, role, QColor(SOFT))
    return palette


def Text(text: str, size: int = 14, bold: bool = False, color: str = TEXT, spacing: float = 0.0,
         align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setFont(Font(size, bold, spacing))
    label.setStyleSheet(f"color: {color};")
    label.setAlignment(align | Qt.AlignmentFlag.AlignVCenter)
    label.setWordWrap(wrap)
    return label


def Kicker(text: str, color: str = GOLD) -> QLabel:
    return Text(text.upper(), 12, True, color, 2.0)


def Rule(width: int = 180) -> QFrame:
    line = QFrame()
    line.setFixedSize(width, 2)
    line.setStyleSheet("background: rgba(255, 255, 255, 0.85);")
    return line


def Section(title: str) -> QVBoxLayout:
    """Chipper's centred block heading with a short white rule under it."""
    box = QVBoxLayout()
    box.setSpacing(12)
    box.addSpacing(14)
    box.addWidget(Text(title.upper(), 40, True, WHITE, 1.6, Qt.AlignmentFlag.AlignHCenter))
    box.addWidget(Rule(), 0, Qt.AlignmentFlag.AlignHCenter)
    return box


def Pixmap(name: str, size: int) -> QPixmap:
    """`size` logical pixels, kept sharp on high-DPI screens (Windows at 125–150% scaling)."""
    ratio = QApplication.instance().devicePixelRatio()
    side = round(size * ratio)
    pixmap = QPixmap(str(ASSETS / name)).scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def AppIcon() -> QIcon:
    """Bee Sid's .ico holds a head-only picture for the smallest sizes; Qt needs its ico plugin to read it."""
    formats = {name.data().decode() for name in QImageReader.supportedImageFormats()}
    return QIcon(str(ASSETS / ("icon.ico" if "ico" in formats else "icon.png")))


def Skewed(box: QRectF, skew: float) -> QPolygonF:
    return QPolygonF([QPointF(box.left() + skew, box.top()), QPointF(box.right(), box.top()),
                      QPointF(box.right() - skew, box.bottom()), QPointF(box.left(), box.bottom())])


def Chamfered(box: QRectF, cut: float) -> QPolygonF:
    left, top, right, bottom = box.left(), box.top(), box.right(), box.bottom()
    return QPolygonF([QPointF(left + cut, top), QPointF(right, top), QPointF(right, bottom - cut),
                      QPointF(right - cut, bottom), QPointF(left, bottom), QPointF(left, top + cut)])


def PaintStars(painter: QPainter, box: QRectF, count: int, seed: int) -> None:
    """A fixed starfield (same seed, same sky) like the one inside Chipper's buttons."""
    rng = random.Random(seed)
    painter.setPen(Qt.PenStyle.NoPen)
    for _ in range(count):
        star = QColor(WHITE)
        star.setAlpha(rng.randint(50, 210))
        painter.setBrush(star)
        radius = rng.choice((0.6, 0.6, 0.9, 1.3))
        painter.drawEllipse(QPointF(box.left() + rng.random() * box.width(),
                                    box.top() + rng.random() * box.height()), radius, radius)


def Sparkle(painter: QPainter, center: QPointF, size: float, color: str) -> None:
    x, y = center.x(), center.y()
    path = QPainterPath(QPointF(x, y - size))
    for dx, dy in ((size, 0), (0, size), (-size, 0), (0, -size)):
        path.quadTo(x, y, x + dx, y + dy)
    painter.fillPath(path, QColor(color))


def Stars(met: int, total: int) -> str:
    return "★" * met + "☆" * (total - met)


def KeyboardFocus(event) -> bool:
    return event.reason() in (Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason)


def Net(report: Report) -> float:
    return float(report.summary.get("net_usd") or 0)


def WinRate(report: Report) -> str:
    return f"{float(report.summary.get('win_rate') or 0):.0%}"


def Clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget() is not None:
            item.widget().hide()
            item.widget().deleteLater()
        elif item.layout() is not None:
            Clear(item.layout())


class SkewButton(QPushButton):
    """Chipper's slanted button: red call to action, starry blue with a glow, thin 'ghost', or a header 'tab'."""

    SKEW = 14

    def __init__(self, text: str, kind: str = "red", color: str = RED, upper: bool = True):
        super().__init__(text.upper() if upper else text)
        self.kind, self.color = kind, QColor(color)
        self.keyboard_focus = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCheckable(kind == "tab")
        self.setFont(Font({"tab": 17, "ghost": 13}.get(kind, 15), True, 0.3 if kind == "tab" else 1.0))
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def Pad(self) -> int:
        return 9 if self.kind == "blue" else 0  # room for the glow

    def sizeHint(self) -> QSize:
        width = QFontMetrics(self.font()).horizontalAdvance(self.text()) + 2 * self.SKEW + 40
        height = {"tab": 64, "ghost": 38, "red": 56}.get(self.kind, 52)
        return QSize(width + 2 * self.Pad(), height + 2 * self.Pad())

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def focusInEvent(self, event) -> None:
        self.keyboard_focus = KeyboardFocus(event)  # the ring is for keyboard users, not window activation
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.keyboard_focus = False
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pad = self.Pad()
        box = QRectF(self.rect()).adjusted(pad + 0.5, pad + 0.5, -pad - 0.5, -pad - 0.5)
        hover, ink = self.underMouse() and self.isEnabled(), QColor(WHITE)
        if self.kind == "red":
            box.setBottom(box.bottom() - 4)  # room for the chunky bottom edge
            p.setPen(Qt.PenStyle.NoPen)
            if self.isDown():
                box.translate(0, 3)
            else:
                p.setBrush(self.color.darker(170))
                p.drawPolygon(Skewed(box.translated(0, 4), self.SKEW))
            p.setBrush(self.color.lighter(118) if hover else self.color)
            p.drawPolygon(Skewed(box, self.SKEW))
        elif self.kind == "blue":
            shape = Skewed(box, self.SKEW)
            p.setBrush(Qt.BrushStyle.NoBrush)
            for width, alpha in ((18, 16), (12, 28), (6, 52)):
                glow = QColor(self.color)
                glow.setAlpha(alpha + (24 if hover else 0))
                p.setPen(QPen(glow, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPolygon(shape)
            fill = QColor(self.color)
            fill.setAlpha(230 if hover else 175)
            p.setPen(QPen(QColor(255, 255, 255, 110), 1))
            p.setBrush(fill)
            p.drawPolygon(shape)
            clip = QPainterPath()
            clip.addPolygon(shape)
            p.save()
            p.setClipPath(clip)
            PaintStars(p, box, 28, 11)
            p.restore()
        elif self.kind == "tab":
            on = self.isChecked()
            top, bottom = QColor(self.color), QColor(self.color)
            top.setAlpha(0)
            bottom.setAlpha(230 if on else 150 if hover else 70)
            fade = QLinearGradient(box.topLeft(), box.bottomLeft())
            fade.setColorAt(0, top)
            fade.setColorAt(1, bottom)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fade)
            p.drawPolygon(Skewed(box, self.SKEW))
            if on:
                p.setBrush(self.color.lighter(140))
                p.drawRect(QRectF(box.left(), box.bottom() - 3, box.width() - self.SKEW, 3))
            ink = QColor(WHITE if on or hover else TEXT)
        else:
            p.setPen(QPen(QColor(GOLD if hover else BORDER_HI), 1.4))
            p.setBrush(QColor(NAVY_3) if hover else Qt.BrushStyle.NoBrush)
            p.drawPolygon(Skewed(box, self.SKEW))
            ink = QColor(GOLD if hover else TEXT)
        if not self.isEnabled():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(7, 13, 33, 160))
            p.drawPolygon(Skewed(box, self.SKEW))
            ink = QColor(SOFT)
        if self.keyboard_focus:
            p.setPen(QPen(QColor(WHITE), 1.2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolygon(Skewed(box.adjusted(6, 4, -6, -4), self.SKEW - 3))
        p.setPen(ink)
        p.setFont(self.font())
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.text())


class Tag(QWidget):
    """A small slanted sticker: slot numbers, ranks, goal results and the simulation badge."""

    def __init__(self, text: str, fill: str, ink: str = NAVY, size: int = 11, outline: bool = False):
        super().__init__()
        self.fill, self.ink, self.outline = QColor(fill), QColor(ink), outline
        self.setFont(Font(size, True, 1.2))
        self.label = text.upper()
        metrics = QFontMetrics(self.font())
        self.setFixedSize(metrics.horizontalAdvance(self.label) + 30, metrics.height() + 8)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6)
        if self.outline:
            p.setPen(QPen(self.fill, 1.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.fill)
        p.drawPolygon(Skewed(box, 7))
        p.setPen(self.ink)
        p.setFont(self.font())
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.label)


def Sticker(text: str, fill: str, size: int = 11) -> Tag:
    return Tag(text, fill, NAVY if fill in DARK_INK else WHITE, size)


class GamePanel(QFrame):
    """A HUD panel with two clipped corners and a coloured strip; clickable ones behave like save slots."""

    clicked = Signal()
    CUT = 14

    def __init__(self, accent: str | None = None, clickable: bool = False):
        super().__init__()
        self.accent = QColor(accent) if accent else None
        self.clickable, self.hovered, self.keyboard_focus = clickable, False, False
        if clickable:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setFocusPolicy(Qt.FocusPolicy.TabFocus)

    def enterEvent(self, event) -> None:
        self.hovered = self.clickable
        self.update()

    def leaveEvent(self, event) -> None:
        self.hovered = False
        self.update()

    def focusInEvent(self, event) -> None:
        self.keyboard_focus = KeyboardFocus(event)
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        self.keyboard_focus = False
        super().focusOutEvent(event)
        self.update()

    def mousePressEvent(self, event) -> None:
        # Accepting the press makes this panel receive the release, even when a child label was clicked.
        if self.clickable and event.button() == Qt.MouseButton.LeftButton:
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if (self.clickable and event.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(event.position().toPoint())):
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:
        if self.clickable and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        fill = QLinearGradient(box.topLeft(), box.bottomLeft())
        fill.setColorAt(0, QColor("#18235a" if self.hovered else "#111a40"))
        fill.setColorAt(1, QColor(NAVY_2))
        lit = self.hovered or self.keyboard_focus
        p.setPen(QPen(QColor(GOLD if lit else BORDER), 1.5 if lit else 1))
        p.setBrush(fill)
        p.drawPolygon(Chamfered(box, self.CUT))
        if self.accent is not None:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.accent)
            p.drawPolygon(Skewed(QRectF(box.left() + self.CUT + 8, box.top(), 96, 5), 5))


class HeaderBar(QFrame):
    def paintEvent(self, event) -> None:
        p = QPainter(self)
        box = QRectF(self.rect())
        shade = QLinearGradient(box.topLeft(), box.bottomLeft())
        shade.setColorAt(0, QColor("#172160"))
        shade.setColorAt(1, QColor("#0a1130"))
        p.fillRect(box, shade)
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(QPointF(0, box.bottom() - 0.5), QPointF(box.right(), box.bottom() - 0.5))


class Hero(QFrame):
    """Chipper's starry hero banner, with Bee Sid standing in the bottom-right corner in a gold glow."""

    def __init__(self, art: int = 270):
        super().__init__()
        self.art = QLabel(self)
        self.art.setPixmap(Pixmap("bee_sid.png", art))
        self.art.adjustSize()
        self.setMinimumHeight(art + 70)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # The source art is cropped at its bottom and right, so it sits flush against those edges.
        self.art.move(self.width() - self.art.width(), self.height() - self.art.height())

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect())
        sky = QLinearGradient(box.topLeft(), box.bottomLeft())
        sky.setColorAt(0, QColor("#141d52"))
        sky.setColorAt(1, QColor(NAVY))
        p.fillRect(box, sky)
        for fx, fy, radius, rgb in ((0.36, 0.42, 380, (122, 60, 255)), (0.08, 0.95, 320, (24, 97, 218))):
            glow = QRadialGradient(QPointF(box.width() * fx, box.height() * fy), radius)
            glow.setColorAt(0, QColor(*rgb, 72))
            glow.setColorAt(1, QColor(*rgb, 0))
            p.fillRect(box, glow)
        PaintStars(p, box, 180, 5)
        rng = random.Random(9)
        for _ in range(8):
            Sparkle(p, QPointF(rng.random() * box.width() * 0.7, rng.random() * box.height() * 0.85),
                    rng.uniform(4, 8), STAR)
        halo = QRadialGradient(QPointF(self.art.geometry().center()), 200)
        halo.setColorAt(0, QColor(229, 200, 125, 130))
        halo.setColorAt(0.5, QColor(229, 200, 125, 45))
        halo.setColorAt(1, QColor(229, 200, 125, 0))
        p.fillRect(box, halo)
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(QPointF(0, box.bottom() - 0.5), QPointF(box.right(), box.bottom() - 0.5))


class Logo(QWidget):
    """'BEE SID' as a bouncy game logo: bee-striped letters in a black and white outline, a soft glow and a red
    DESK sticker."""

    TILT = (-7, 5, -4, 6, -5, 4)
    LIFT = (5, -3, 6, -4, 3, -2)

    def __init__(self, word: str = "BEE SID", size: int = 104):
        super().__init__()
        self.zoom = size / 104  # outline, glow and sticker sizes were tuned at 104 px
        pad = 26 * self.zoom
        font = Font(size, True)
        metrics = QFontMetricsF(font)
        self.letters: list[tuple[QPainterPath, QTransform]] = []
        x, bounds = 0.0, QRectF()
        for char in word:
            if char == " ":
                x += metrics.horizontalAdvance(char)
                continue
            index = len(self.letters) % len(self.TILT)
            path = QPainterPath()
            path.addText(x, metrics.ascent(), font, char)
            mid = path.boundingRect().center()
            turn = QTransform().translate(mid.x(), mid.y() + self.LIFT[index] * self.zoom)
            turn.rotate(self.TILT[index]).translate(-mid.x(), -mid.y())
            self.letters.append((path, turn))
            bounds = bounds.united(turn.mapRect(path.boundingRect()))
            x += metrics.horizontalAdvance(char) + size * 0.07
        self.origin = QPointF(pad - bounds.left(), pad - bounds.top())
        self.tag_font = Font(max(14, size // 4), True, 5.0 * self.zoom)
        tag = QFontMetricsF(self.tag_font)
        self.tag = QRectF(0, 0, tag.horizontalAdvance("DESK") + 44 * self.zoom, tag.height() + 12 * self.zoom)
        self.tag.moveTopRight(QPointF(pad + bounds.width() + 8 * self.zoom,
                                      pad + bounds.height() - self.tag.height() * 0.3))
        self.setFixedSize(int(bounds.width() + 2 * pad + 12 * self.zoom), int(self.tag.bottom() + 10 * self.zoom))

    @staticmethod
    def Stripes(box: QRectF) -> QLinearGradient:
        """Bee Sid's yellow with a black band across the middle, at the same height on every capital."""
        fill = QLinearGradient(box.topLeft(), box.bottomLeft())
        for at, color in ((0.0, BEE_LIGHT), (0.36, BEE), (0.361, INK), (0.6, INK), (0.601, BEE), (1.0, BEE_DARK)):
            fill.setColorAt(at, QColor(color))
        return fill

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.save()
        p.translate(self.origin)
        round_pen = (Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        halo = QPainterPath()
        for path, turn in self.letters:
            halo.addPath(turn.map(path))
        for width, alpha in ((46, 12), (34, 22), (26, 38)):
            p.strokePath(halo, QPen(QColor(255, 255, 255, alpha), width * self.zoom, *round_pen))
        for path, turn in self.letters:
            p.save()
            p.setTransform(turn, True)  # the stripes tilt with each letter
            p.strokePath(path, QPen(QColor(WHITE), 14 * self.zoom, *round_pen))
            p.strokePath(path, QPen(QColor(INK), 6 * self.zoom, *round_pen))
            p.fillPath(path, self.Stripes(path.boundingRect()))
            p.restore()
        p.restore()
        center = self.tag.center()
        p.translate(center)
        p.rotate(-4)
        p.translate(-center)
        p.setPen(QPen(QColor(NAVY), 3 * self.zoom))
        p.setBrush(QColor(RED))
        p.drawPolygon(Skewed(self.tag, 12 * self.zoom))
        p.setPen(QColor(WHITE))
        p.setFont(self.tag_font)
        p.drawText(self.tag, Qt.AlignmentFlag.AlignCenter, "DESK")


class EquityChart(QWidget):
    """Closed-trade equity drawn natively: a gold line, green above zero and red below, a dot for each trade."""

    def __init__(self):
        super().__init__()
        self.curve: list[tuple[str, float, float]] = []
        self.setMinimumHeight(270)

    def SetCurve(self, curve: list[tuple[str, float, float]]) -> None:
        self.curve = curve
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(Font(11, True))
        if not self.curve:
            p.setPen(QColor(SOFT))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No closed trades in this run.")
            return
        area = QRectF(self.rect()).adjusted(72, 12, -18, -30)
        totals = [0.0] + [total for *_, total in self.curve]
        pad = (max(totals) - min(totals)) * 0.08 or 100.0
        low, high = min(totals) - pad, max(totals) + pad

        def X(index: int) -> float:
            return area.left() + area.width() * index / (len(totals) - 1)

        def Y(value: float) -> float:
            return area.bottom() - area.height() * (value - low) / (high - low)

        step = NiceStep(high - low)
        value = math.ceil(low / step) * step
        while value <= high:
            p.setPen(QPen(QColor(BORDER), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(area.left(), Y(value)), QPointF(area.right(), Y(value)))
            p.setPen(QColor(SOFT))
            p.drawText(QRectF(0, Y(value) - 9, area.left() - 12, 18),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, Money(value))
            value += step
        zero = Y(0.0)
        line = QPainterPath(QPointF(X(0), zero))
        for index, total in enumerate(totals[1:], 1):
            line.lineTo(X(index), Y(total))
        fill = QPainterPath(line)
        fill.lineTo(X(len(totals) - 1), zero)
        fill.closeSubpath()
        for color, edge, clip in ((UP, area.top(), QRectF(area.left(), 0, area.width(), zero)),
                                  (DOWN, area.bottom(), QRectF(area.left(), zero, area.width(), self.height()))):
            shade = QLinearGradient(0, zero, 0, edge)
            faint, strong = QColor(color), QColor(color)
            faint.setAlpha(8)
            strong.setAlpha(95)
            shade.setColorAt(0, faint)
            shade.setColorAt(1, strong)
            p.save()
            p.setClipRect(clip)
            p.fillPath(fill, shade)
            p.restore()
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        p.drawLine(QPointF(area.left(), zero), QPointF(area.right(), zero))
        p.strokePath(line, QPen(QColor(GOLD), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                                Qt.PenJoinStyle.RoundJoin))
        p.setPen(QPen(QColor(NAVY), 1.5))
        for index, (_, pnl, total) in enumerate(self.curve, 1):
            p.setBrush(QColor(UP if pnl > 0 else DOWN))
            p.drawEllipse(QPointF(X(index), Y(total)), 4.5, 4.5)
        p.setPen(QColor(SOFT))
        below = QRectF(area.left(), area.bottom() + 8, area.width(), 18)
        p.drawText(below, Qt.AlignmentFlag.AlignLeft, self.curve[0][0])
        p.drawText(below, Qt.AlignmentFlag.AlignRight, self.curve[-1][0])


class Bubble(QFrame):
    """Bee Sid's cream speech bubble, its tail pointing up at his portrait."""

    TAIL = 14

    def __init__(self):
        super().__init__()
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(22, 18 + self.TAIL, 22, 18)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1.5, self.TAIL + 1.5, -1.5, -1.5)
        shape = QPainterPath()
        shape.addRoundedRect(box, 16, 16)
        mid = box.center().x()
        tail = QPainterPath()
        tail.addPolygon(QPolygonF([QPointF(mid - 14, box.top() + 3), QPointF(mid, box.top() - self.TAIL),
                                   QPointF(mid + 14, box.top() + 3)]))
        tail.closeSubpath()
        p.setPen(QPen(QColor(GOLD), 2.5))
        p.setBrush(QColor(CREAM))
        p.drawPath(shape.united(tail))


class BacktestWorker(QThread):
    completed = Signal(bool, str)

    def __init__(self, args: list[str], staging: Path, out: Path, data_dir: Path | None):
        super().__init__()
        self.args = args
        self.staging = staging
        self.out = out
        self.data_dir = data_dir

    def run(self) -> None:
        try:
            from . import data as D
            from .cli import Main as CliMain

            if self.data_dir is not None:
                D.DATA_DIR = self.data_dir
            shutil.rmtree(self.staging, ignore_errors=True)
            with redirect_stdout(StringIO()):
                CliMain(self.args)
            Publish(self.staging, self.out)
        except (Exception, SystemExit) as exc:
            shutil.rmtree(self.staging, ignore_errors=True)
            self.completed.emit(False, f"That run failed: {exc}")
        else:
            self.completed.emit(True, "")


class Desk(QMainWindow):
    HOME, RUNS, REPORT, NEW_RUN = range(4)

    def __init__(self, paths: Paths):
        super().__init__()
        LoadFonts()
        self.paths = paths
        self.worker: BacktestWorker | None = None
        self.pending, self.pending_title = LATEST, "Latest Run"
        self.reports: list[Report] = []
        self.slot_cards: list[GamePanel] = []
        self.current: Report | None = None
        self.setWindowTitle("Bee Sid")
        self.resize(1240, 820)
        self.setMinimumSize(1000, 680)

        body = QWidget()
        self.setCentralWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.MakeHeader())
        layout.addWidget(self.MakeHud())
        self.pages = QStackedWidget()
        for page in (self.MakeHome(), self.MakeRuns(), self.MakeReport(), self.MakeRunner()):
            self.pages.addWidget(page)
        layout.addWidget(self.pages, 1)
        self.Refresh()
        self.Show(self.HOME)

    # ---------------------------------------------------------------- frame
    def MakeHeader(self) -> QFrame:
        bar = HeaderBar()
        bar.setFixedHeight(64)
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 0, 20, 0)
        row.setSpacing(0)
        emblem = QLabel()
        emblem.setPixmap(Pixmap("icon.png", 42))
        row.addWidget(emblem)
        row.addSpacing(10)
        row.addWidget(Text("Bee Sid", 24, True, WHITE, wrap=False))
        row.addSpacing(30)
        self.nav = QButtonGroup(self)
        for index, (label, color) in enumerate((("Home", BLUE), ("Saved runs", PURPLE), ("New backtest", RED))):
            tab = SkewButton(label, "tab", color, upper=False)
            self.nav.addButton(tab, index)
            row.addWidget(tab)
            row.addSpacing(6)
        self.nav.idClicked.connect(self.Tab)
        row.addStretch()
        row.addWidget(Tag("● Simulation only", UP, UP, 11, outline=True))
        return bar

    def MakeHud(self) -> QFrame:
        hud = QFrame()
        hud.setObjectName("hud")
        row = QHBoxLayout(hud)
        row.setContentsMargins(24, 7, 24, 7)
        row.setSpacing(28)
        self.hud = [Text("", 12, True, SOFT, 1.0, wrap=False) for _ in range(4)]
        for label in self.hud:
            row.addWidget(label)
        row.addStretch()
        return hud

    def Scroller(self) -> tuple[QScrollArea, QVBoxLayout, QVBoxLayout]:
        """A scrolling page: `outer` spans the full width, `column` is centred and capped for reading."""
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        holder = QWidget()
        holder.setMaximumWidth(1100)
        column = QVBoxLayout(holder)
        column.setContentsMargins(28, 22, 28, 40)
        column.setSpacing(16)
        center = QHBoxLayout()
        center.addStretch()
        center.addWidget(holder, 1)
        center.addStretch()
        outer.addLayout(center)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll, outer, column

    def Panel(self, title: str, accent: str) -> tuple[GamePanel, QVBoxLayout, QLabel]:
        panel = GamePanel(accent)
        box = QVBoxLayout(panel)
        box.setContentsMargins(22, 22, 22, 20)
        box.setSpacing(12)
        head = QHBoxLayout()
        head.addWidget(Text(title.upper(), 20, True, WHITE, 1.4, wrap=False))
        head.addStretch()
        note = Text("", 13, True, SOFT, wrap=False)
        head.addWidget(note)
        box.addLayout(head)
        return panel, box, note

    # ---------------------------------------------------------------- pages
    def MakeHome(self) -> QScrollArea:
        scroll, outer, column = self.Scroller()
        hero = Hero()
        brand = QVBoxLayout(hero)
        brand.setContentsMargins(40, 26, hero.art.width() + 30, 30)
        brand.setSpacing(14)
        brand.addWidget(Logo(), 0, Qt.AlignmentFlag.AlignHCenter)
        buttons = QHBoxLayout()
        buttons.setSpacing(18)
        buttons.addStretch()
        start = SkewButton("▶  New backtest", "red")
        start.clicked.connect(lambda: self.Show(self.NEW_RUN))
        runs = SkewButton("Saved runs", "blue", BLUE)
        runs.clicked.connect(lambda: self.Tab(1))
        buttons.addWidget(start)
        buttons.addWidget(runs)
        buttons.addStretch()
        brand.addLayout(buttons)
        outer.insertWidget(0, hero)

        center = Qt.AlignmentFlag.AlignHCenter
        column.addLayout(Section("Read. Wait. Sting."))
        column.addWidget(Text("Welcome to Bee Sid's HQ, where the Bias + OTE plan gets tested on real NQ history "
                              "without risking a cent.".upper(), 20, True, WHITE, 0.6, center))
        column.addWidget(Text("Pick a period, press start and read the honest numbers: net P&L, win rate, "
                              "drawdown and every single trade.", 16, False, TEXT, align=center))
        reviews = QWidget()
        reviews.setFixedWidth(620)
        stack = QVBoxLayout(reviews)
        stack.setContentsMargins(0, 8, 0, 0)
        stack.setSpacing(14)
        stack.addWidget(Text(f"<span style='color:{STAR}'>★</span>&nbsp;&nbsp;REVIEWS", 14, True, WHITE, 2.0))
        for quote, cite, score in (("“Best backtest desk in the hive.”", "(According to its protagonist)", ""),
                                   ("“Can't place a real order even if you beg.”", "The safety rails", "100/10")):
            card = QFrame()
            card.setObjectName("review")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 6, 6, 6)
            box.setSpacing(4)
            top = QHBoxLayout()
            top.addWidget(Text("★★★★★", 14, False, STAR, wrap=False))
            top.addStretch()
            if score:
                top.addWidget(Text(score, 14, True, STAR, wrap=False))
            box.addLayout(top)
            box.addWidget(Text(quote, 17, True, WHITE))
            box.addWidget(Text(cite, 13, True, SOFT))
            stack.addWidget(card)
        column.addWidget(reviews, 0, center)

        column.addLayout(Section("Leaderboard"))
        column.addWidget(Text("Ranked by net P&L after costs. Past results, not promises.", 14, False, SOFT,
                              align=center))
        self.board = QVBoxLayout()
        self.board.setSpacing(10)
        column.addLayout(self.board)
        column.addLayout(Section("House rules"))
        rules = Text(RULES, 17, False, TEXT, align=center)
        rules.setFixedWidth(820)
        column.addWidget(rules, 0, center)
        column.addStretch()
        return scroll

    def MakeRuns(self) -> QScrollArea:
        scroll, _, column = self.Scroller()
        center = Qt.AlignmentFlag.AlignHCenter
        column.addLayout(Section("Saved runs"))
        column.addWidget(Text("Pick a save slot to open its report.", 15, False, SOFT, align=center))
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addStretch()
        start = SkewButton("▶  New backtest", "red")
        start.clicked.connect(lambda: self.Show(self.NEW_RUN))
        folder = SkewButton("Open runs folder", "ghost")
        folder.clicked.connect(self.OpenRuns)
        row.addWidget(start)
        row.addWidget(folder, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch()
        column.addLayout(row)
        column.addSpacing(6)
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        for index in range(3):
            self.grid.setColumnStretch(index, 1)
        column.addLayout(self.grid)
        self.empty = Text("No saved runs yet. Start one from New backtest.", 15, False, SOFT, align=center)
        column.addWidget(self.empty)
        column.addStretch()
        return scroll

    def MakeReport(self) -> QScrollArea:
        scroll, _, column = self.Scroller()
        top = QHBoxLayout()
        back = SkewButton("◀  All runs", "ghost")
        back.clicked.connect(lambda: self.Show(self.RUNS))
        self.full_chart = SkewButton("Open full chart", "ghost")
        self.full_chart.clicked.connect(self.OpenChart)
        top.addWidget(back)
        top.addStretch()
        top.addWidget(self.full_chart)
        column.addLayout(top)
        column.addWidget(Kicker("Saved run  ·  historical simulation"))
        self.report_title = Text("", 40, True, WHITE)
        self.report_hint = Text("", 14, False, SOFT)
        column.addWidget(self.report_title)
        column.addWidget(self.report_hint)

        tiles = QGridLayout()
        tiles.setSpacing(14)
        self.stats: list[tuple[QLabel, QLabel]] = []
        headings = (("Net P&L", GREEN), ("Win rate", BLUE), ("Max drawdown", RED), ("Trades", PURPLE))
        for index, (heading, accent) in enumerate(headings):
            tile = GamePanel(accent)
            box = QVBoxLayout(tile)
            box.setContentsMargins(20, 20, 20, 16)
            box.setSpacing(2)
            box.addWidget(Kicker(heading, SOFT))
            number, note = Text("—", 30, True, WHITE, wrap=False), Text("", 12, False, SOFT)
            box.addWidget(number)
            box.addWidget(note)
            self.stats.append((number, note))
            tiles.addWidget(tile, 0, index)
        column.addLayout(tiles)
        self.extras = Text("", 13, True, SOFT, 0.8)
        column.addWidget(self.extras)

        chart_panel, chart_box, chart_note = self.Panel("Equity", GOLD)
        chart_note.setText("CLOSED TRADES, AFTER COSTS")
        self.chart = EquityChart()
        chart_box.addWidget(self.chart)
        column.addWidget(chart_panel)

        goals_panel, goals_box, self.goal_score = self.Panel("Goals", STAR)
        self.goal_score.setStyleSheet(f"color: {STAR};")
        self.goal_grid = QGridLayout()
        self.goal_grid.setSpacing(12)
        goals_box.addLayout(self.goal_grid)
        column.addWidget(goals_panel)

        trades_panel, trades_box, _ = self.Panel("Recent trades", CYAN)
        self.trades = QTableWidget(0, 5)
        self.trades.setHorizontalHeaderLabels(["ENTRY (ET)", "BOOK", "SIDE", "P&L", "EXIT"])
        header = self.trades.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.trades.verticalHeader().setVisible(False)
        self.trades.setAlternatingRowColors(True)
        self.trades.setShowGrid(False)
        self.trades.setFrameShape(QFrame.Shape.NoFrame)
        self.trades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.trades.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.trades.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        trades_box.addWidget(self.trades)
        column.addWidget(trades_panel)
        column.addWidget(Text("Historical simulations are not live results or a guarantee of future performance.",
                              12, False, SOFT))
        column.addStretch()
        return scroll

    def MakeRunner(self) -> QScrollArea:
        scroll, _, column = self.Scroller()
        center = Qt.AlignmentFlag.AlignHCenter
        column.addLayout(Section("New backtest"))
        column.addWidget(Text("Set up a run and press start: Bee Sid replays it on history. He can't place orders.",
                              15, False, SOFT, align=center))
        row = QHBoxLayout()
        row.setSpacing(28)
        panel, box, _ = self.Panel("Run setup", RED)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.run_name = QLineEdit()
        self.run_name.setMaxLength(60)
        self.run_name.setPlaceholderText("Latest Run  (type a name to keep this run)")
        self.start = QLineEdit("2025-07-26")
        self.start.setPlaceholderText("YYYY-MM-DD")
        self.end = QLineEdit()
        self.end.setPlaceholderText("YYYY-MM-DD  (blank = up to the latest data)")
        self.base = self.Choice(("1h  ·  swing and hourly books", "1h"), ("5m  ·  adds the 5m scalp book", "5m"),
                                ("1m  ·  adds the teacher 1m book", "1m"))
        self.mode = self.Choice(("As configured", "config"), ("Prop  ·  flat every day", "prop"),
                                ("Swing  ·  may hold overnight", "swing"))
        self.source = self.Choice(("Yahoo", "yahoo"), ("IBKR history (from rapier ibkr-backfill)", "ibkr"))
        self.cached = QCheckBox("Reuse saved market data (skip re-downloading)")
        self.cached.setChecked(True)
        for label, field in (("Run name", self.run_name), ("Start date", self.start), ("End date", self.end),
                             ("Clock", self.base), ("Risk mode", self.mode), ("Market data", self.source),
                             ("", self.cached)):
            caption = Text(label.upper(), 12, True, SOFT, 1.2, wrap=False)
            caption.setMinimumHeight(field.sizeHint().height())
            form.addRow(caption, field)
        box.addLayout(form)
        row.addWidget(panel, 3)
        npc = QVBoxLayout()
        npc.setSpacing(8)
        portrait = QLabel()
        portrait.setPixmap(Pixmap("icon.png", 150))
        npc.addWidget(portrait, 0, center)
        npc.addWidget(Tag("Bee Sid", GOLD, NAVY, 13), 0, center)
        bubble = Bubble()
        self.status = Text(INTRO, 15, False, NAVY_2)
        bubble.body.addWidget(self.status)
        npc.addWidget(bubble)
        npc.addStretch()
        row.addLayout(npc, 2)
        column.addLayout(row)
        column.addSpacing(6)
        self.launch = SkewButton("▶  Start run", "red")
        self.launch.clicked.connect(self.RunBacktest)
        column.addWidget(self.launch, 0, center)
        column.addStretch()
        return scroll

    def Choice(self, *options: tuple[str, str]) -> QComboBox:
        box = QComboBox()
        for text, value in options:
            box.addItem(text, value)
        return box

    # ---------------------------------------------------------------- cards
    def SlotCard(self, index: int, report: Report) -> GamePanel:
        color = SLOT_COLORS[index % len(SLOT_COLORS)]
        card = GamePanel(color, clickable=True)
        card.report = report
        card.clicked.connect(lambda: self.OpenReport(report))
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 20, 20, 16)
        box.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(Sticker(f"Slot {index + 1:02d}", color, 10))
        top.addStretch()
        top.addWidget(Text(Stars(*GoalScore(report.goals)), 15, False, STAR, wrap=False))
        box.addLayout(top)
        box.addSpacing(6)
        box.addWidget(Text(report.title, 19, True, WHITE))
        box.addWidget(Text(report.dates or "Saved run", 12, False, SOFT))
        box.addSpacing(10)
        stats = QHBoxLayout()
        stats.setSpacing(18)
        net = Net(report)
        for value, label, ink in ((Money(net, True), "Net P&L", UP if net >= 0 else DOWN),
                                  (WinRate(report), "Win rate", WHITE),
                                  (str(report.summary.get("trades", 0)), "Trades", WHITE)):
            cell = QVBoxLayout()
            cell.setSpacing(0)
            cell.addWidget(Text(value, 20, True, ink, wrap=False))
            cell.addWidget(Text(label.upper(), 10, True, SOFT, 1.2, wrap=False))
            stats.addLayout(cell)
        stats.addStretch()
        box.addLayout(stats)
        box.addStretch()
        return card

    def LeaderRow(self, rank: int, report: Report) -> GamePanel:
        row = GamePanel(clickable=True)
        row.report = report
        row.clicked.connect(lambda: self.OpenReport(report))
        line = QHBoxLayout(row)
        line.setContentsMargins(20, 12, 24, 12)
        line.setSpacing(18)
        medal = (GOLD, SILVER, BRONZE)[rank - 1] if rank <= 3 else BORDER_HI
        line.addWidget(Sticker(f"#{rank}", medal, 14))
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(Text(report.title, 16, True, WHITE, wrap=False))
        names.addWidget(Text(report.dates or "Saved run", 12, False, SOFT, wrap=False))
        line.addLayout(names, 1)
        net = Net(report)
        for text, ink, width in ((Stars(*GoalScore(report.goals)), STAR, 80),
                                 (f"{WinRate(report)} WIN", TEXT, 90),
                                 (Money(net, True), UP if net >= 0 else DOWN, 100)):
            label = Text(text, 16, True, ink, align=Qt.AlignmentFlag.AlignRight, wrap=False)
            label.setMinimumWidth(width)
            line.addWidget(label)
        return row

    def GoalBadge(self, goal: str, met: bool) -> GamePanel:
        badge = GamePanel()
        line = QHBoxLayout(badge)
        line.setContentsMargins(18, 12, 18, 12)
        line.setSpacing(12)
        line.addWidget(Text("★" if met else "☆", 26, False, STAR if met else SOFT, wrap=False))
        line.addWidget(Text(GoalLabel(goal), 14, True, WHITE if met else TEXT), 1)
        line.addWidget(Tag("Met", UP, NAVY, 10) if met else Tag("Not met", SOFT, SOFT, 10, outline=True))
        return badge

    # ---------------------------------------------------------------- actions
    def Tab(self, index: int) -> None:
        if index == 1:
            self.Refresh()
        self.Show((self.HOME, self.RUNS, self.NEW_RUN)[index])

    def Show(self, page: int) -> None:
        self.pages.setCurrentIndex(page)
        self.nav.button((0, 1, 1, 2)[page]).setChecked(True)

    def OpenRuns(self) -> None:
        self.paths.runs.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.runs)))

    def OpenChart(self) -> None:
        if self.current is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current.folder / "equity.png")))

    def Refresh(self, select: str | None = None) -> None:
        self.reports = LoadReports(self.paths.runs, self.paths.samples)
        Clear(self.grid)
        self.slot_cards = [self.SlotCard(index, report) for index, report in enumerate(self.reports)]
        for index, card in enumerate(self.slot_cards):
            self.grid.addWidget(card, index // 3, index % 3)
        self.empty.setVisible(not self.reports)
        Clear(self.board)
        for rank, report in enumerate(sorted(self.reports, key=Net, reverse=True)[:5], 1):
            self.board.addWidget(self.LeaderRow(rank, report))
        best = max(self.reports, key=Net, default=None)
        facts = ((STAR, "★", f"{len(self.reports)} saved runs"),
                 (UP, "▲", f"best run {Money(Net(best), True)}" if best else "no runs yet"),
                 (GOLD, "◆", "every trade planned at 1R or better"),
                 (CYAN, "●", "never places real orders"))
        for label, (color, glyph, fact) in zip(self.hud, facts):
            label.setText(f"<span style='color:{color}'>{glyph}</span>&nbsp;&nbsp;{fact.upper()}")
        match = next((report for report in self.reports if report.name == select), None)
        if match is not None:
            self.OpenReport(match)

    def OpenReport(self, report: Report) -> None:
        self.current = report
        s = report.summary
        self.report_title.setText(report.title)
        self.report_hint.setText("  ·  ".join(filter(None, (report.dates, "historical simulation, not live results"))))
        net = Net(report)
        values = (Money(net, True), WinRate(report), Money(float(s.get("max_dd_usd") or 0)), str(s.get("trades", 0)))
        notes = ("after costs", "of closed trades", "intrabar worst", "completed trades")
        for (number, note), value, caption in zip(self.stats, values, notes):
            number.setText(value)
            note.setText(caption.upper())
        self.stats[0][0].setStyleSheet(f"color: {UP if net >= 0 else DOWN};")
        factor = float(s.get("profit_factor") or 0)
        extras = (("Profit factor", f"{factor:.2f}" if math.isfinite(factor) else "∞"),
                  ("Best trade", Money(float(s.get("best_trade_usd") or 0), True)),
                  ("Worst trade", Money(float(s.get("worst_trade_usd") or 0))),
                  ("Longest losing streak", str(s.get("max_consec_losses", 0))))
        self.extras.setText("&nbsp;&nbsp;&nbsp;·&nbsp;&nbsp;&nbsp;".join(
            f"{name.upper()}&nbsp;&nbsp;<span style='color:{WHITE}'>{value}</span>" for name, value in extras))
        self.chart.SetCurve(EquityCurve(report.trades))
        self.full_chart.setVisible((report.folder / "equity.png").exists())
        Clear(self.goal_grid)
        met, total = GoalScore(report.goals)
        self.goal_score.setText(f"{Stars(met, total)}   {met} / {total} MET")
        for index, (goal, ok) in enumerate(report.goals.items()):
            self.goal_grid.addWidget(self.GoalBadge(str(goal), bool(ok)), index // 2, index % 2)
        recent = list(reversed(report.trades[-12:]))
        self.trades.setRowCount(len(recent))
        for row, trade in enumerate(recent):
            pnl = float(trade.get("pnl") or 0)
            cells = ((trade.get("entry_time") or "")[:16], trade.get("book") or "",
                     "LONG" if trade.get("side") == "1" else "SHORT",
                     f"{'-' if pnl < 0 else '+'}${abs(pnl):,.2f}", trade.get("exit_reason") or "")
            for col, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                if col == 3:
                    cell.setForeground(QColor(UP if pnl >= 0 else DOWN))
                self.trades.setItem(row, col, cell)
        self.trades.resizeRowsToContents()
        rows = sum(self.trades.rowHeight(index) for index in range(self.trades.rowCount()))
        self.trades.setFixedHeight(self.trades.horizontalHeader().sizeHint().height() + rows + 4)
        self.Show(self.REPORT)
        self.pages.widget(self.REPORT).verticalScrollBar().setValue(0)

    def RunBacktest(self) -> None:
        folder = RunFolder(self.run_name.text())
        out = self.paths.runs / folder
        staging = Staging(out)
        try:
            args = BacktestArgs(self.start.text().strip(), self.end.text().strip(), self.base.currentData(),
                                self.mode.currentData(), self.source.currentData(), self.cached.isChecked(),
                                staging)
        except ValueError as exc:
            QMessageBox.warning(self, "Check the settings", str(exc))
            return
        title = DisplayName(folder)[0]
        if folder != LATEST and out.exists():
            answer = QMessageBox.question(self, "Replace saved run?", f"“{title}” already exists. Replace it?")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.pending, self.pending_title = folder, title
        self.launch.setEnabled(False)
        self.status.setText(f"Crunching “{title}”… Go look around; I'll open the report when it's done.")
        self.worker = BacktestWorker(args, staging, out, self.paths.data)
        self.worker.completed.connect(self.FinishBacktest)
        self.worker.start()

    def FinishBacktest(self, ok: bool, message: str) -> None:
        self.launch.setEnabled(True)
        if not ok:
            self.status.setText(message)
            return
        self.status.setText(f"Done! “{self.pending_title}” is saved with your runs. Want another go?")
        self.Refresh(select=self.pending)

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Backtest running", "Wait for the backtest to finish before closing.")
            event.ignore()
        else:
            event.accept()


def _CloseSplash() -> None:
    try:
        import pyi_splash  # only exists inside a packaged build that has a startup splash
    except ImportError:
        return
    pyi_splash.close()


def Main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Bee Sid")
    app.setStyle("Fusion")
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme"):
        hints.setColorScheme(Qt.ColorScheme.Dark)  # dark window frame to match, where the OS supports it
    LoadFonts()
    app.setFont(Font(14))
    app.setPalette(Palette())
    app.setStyleSheet(STYLE)
    app.setWindowIcon(AppIcon())
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if getattr(sys, "frozen", False) else None
    user_data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
    if bundle is not None:
        AdoptOldHome(user_data)
    window = Desk(AppPaths(Path(__file__).resolve().parent.parent, bundle, user_data))
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        # Lets the build prove the packaged app starts, finds its example runs, saves outside the unpack folder,
        # and can run the engine and write a report with everything it imports lazily.
        with tempfile.TemporaryDirectory() as tmp:
            trades = EngineCheck(Path(tmp))
            files = sorted(p.name for p in Path(tmp).iterdir())
        report = {"reports": [r.title for r in window.reports], "runs": str(window.paths.runs),
                  "data": str(window.paths.data), "engine_trades": trades, "report_files": files}
        Path(sys.argv[2]).write_text(json.dumps(report), encoding="utf-8")
        return
    window.show()
    _CloseSplash()
    sys.exit(app.exec())


if __name__ == "__main__":
    Main()

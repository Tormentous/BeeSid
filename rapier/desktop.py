"""Rapier Desk: a native Windows/Linux dashboard for saved backtests and new backtest runs (never live orders)."""

from __future__ import annotations

import html
import json
import shutil
import sys
import tempfile
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PySide6.QtCore import QSize, QStandardPaths, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontMetrics, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QFormLayout, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QMainWindow, QMessageBox, QPushButton, QScrollArea, QStackedWidget, QStyle,
                               QStyledItemDelegate, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from .desktop_data import (LATEST, AppPaths, BacktestArgs, DisplayName, EngineCheck, LoadReports, Paths, Publish,
                           Report, RunFolder, Staging)

ASSETS = Path(__file__).resolve().parent / "assets"
CHECK = (ASSETS / "check.svg").as_posix()

# LabradorSim's France desk palette (hue 228): royal navy surfaces, cream text, gold accents.
NAVY, CARD, RAISED, MUTED, BORDER = "#070d21", "#0e1634", "#121b40", "#18234e", "#273468"
CREAM, SOFT, GOLD, GOLD_2 = "#f5edd8", "#b2b6c7", "#e5c87d", "#f0d6a0"
UP, DOWN = "#34d399", "#f87171"
SERIF = "'Source Serif 4', Georgia, 'Times New Roman', 'DejaVu Serif', serif"

STYLE = f"""
QWidget {{ background: {NAVY}; color: {CREAM}; font-size: 13px;
          font-family: 'Source Sans 3', 'Segoe UI', 'Noto Sans', 'DejaVu Sans', sans-serif; }}
QLabel {{ background: transparent; }}
QFrame#side {{ border-right: 1px solid {BORDER}; }}
QFrame#card, QFrame#panel {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 16px; }}
QLabel#brand {{ font-family: {SERIF}; font-size: 22px; font-weight: 700; }}
QLabel#eyebrow {{ color: {SOFT}; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }}
QLabel#title {{ color: {GOLD}; font-family: {SERIF}; font-size: 32px; font-weight: 700; }}
QLabel#heading {{ color: {GOLD}; font-family: {SERIF}; font-size: 19px; font-weight: 700; }}
QLabel#number {{ font-size: 28px; font-weight: 700; }}
QLabel#muted {{ color: {SOFT}; }}
QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 10px 16px;
              font-weight: 600; }}
QPushButton:hover {{ border-color: {GOLD}; }}
QPushButton:disabled {{ color: {SOFT}; background: {MUTED}; }}
QPushButton#nav {{ background: transparent; border: 0; text-align: left; padding: 11px 14px; }}
QPushButton#nav:hover {{ background: {CARD}; }}
QPushButton#nav:checked, QPushButton#primary {{ background: {GOLD}; color: {NAVY}; font-weight: 700; }}
QPushButton#primary {{ border: 0; padding: 12px 18px; }}
QPushButton#primary:hover {{ background: {GOLD_2}; }}
QLineEdit, QComboBox, QTableWidget {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 10px;
                                      padding: 7px; selection-background-color: {MUTED}; }}
QLineEdit:focus, QComboBox:focus {{ border-color: {GOLD}; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {BORDER};
                               selection-background-color: {GOLD}; selection-color: {NAVY}; }}
QComboBox::drop-down {{ border: 0; width: 26px; background: transparent; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QTableWidget {{ gridline-color: {BORDER}; alternate-background-color: {CARD}; }}
QHeaderView::section {{ background: {MUTED}; color: {SOFT}; padding: 8px; border: 0; font-weight: 700; }}
QCheckBox {{ spacing: 8px; background: transparent; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {BORDER}; border-radius: 4px;
                        background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {GOLD}; border-color: {GOLD}; image: url("{CHECK}"); }}
QScrollArea {{ border: 0; }}
QScrollBar:vertical {{ background: transparent; width: 9px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 25px; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; }}
QScrollBar::handle:horizontal {{ background: {BORDER}; border-radius: 4px; min-width: 25px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
"""


def Label(text: str, kind: str = "muted") -> QLabel:
    label = QLabel(text)
    label.setObjectName(kind)
    label.setWordWrap(True)
    return label


def Panel(eyebrow: str, heading: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(22, 18, 22, 20)
    layout.setSpacing(10)
    layout.addWidget(Label(eyebrow, "eyebrow"))
    layout.addWidget(Label(heading, "heading"))
    return frame, layout


def Choice(*options: tuple[str, str]) -> QComboBox:
    box = QComboBox()
    for text, value in options:
        box.addItem(text, value)
    return box


class SlotDelegate(QStyledItemDelegate):
    """Draws a saved run like a save slot: its name over a smaller date line."""

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        box = option.rect.adjusted(0, 3, -2, -3)
        if selected or option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(GOLD if selected else CARD))
            painter.drawRoundedRect(box, 10, 10)
        text = box.adjusted(12, 6, -10, -6)
        title = QFont(option.font)
        title.setPixelSize(14)
        title.setBold(True)
        painter.setFont(title)
        painter.setPen(QColor(NAVY if selected else CREAM))
        name = QFontMetrics(title).elidedText(index.data(Qt.ItemDataRole.DisplayRole),
                                              Qt.TextElideMode.ElideRight, text.width())
        painter.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, name)
        dates = index.data(Qt.ItemDataRole.UserRole)
        if dates:
            small = QFont(option.font)
            small.setPixelSize(12)
            painter.setFont(small)
            painter.setPen(QColor(MUTED if selected else SOFT))
            painter.drawText(text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, dates)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(200, 58)


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
            self.completed.emit(False, f"Backtest failed: {exc}")
        else:
            self.completed.emit(True, "Backtest complete. It is now in your saved runs.")


class Desk(QMainWindow):
    def __init__(self, paths: Paths):
        super().__init__()
        self.paths = paths
        self.worker: BacktestWorker | None = None
        self.pending = LATEST
        self.reports: list[Report] = []
        self.setWindowTitle("Rapier Desk")
        self.resize(1220, 800)
        self.setMinimumSize(980, 660)

        body = QWidget()
        self.setCentralWidget(body)
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)
        columns.addWidget(self.MakeSidebar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self.MakeOverview())
        self.pages.addWidget(self.MakeRunner())
        columns.addWidget(self.pages, 1)
        self.Refresh()
        self.Show(0)

    def MakeSidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("side")
        sidebar.setFixedWidth(272)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 22, 18, 20)
        side.setSpacing(10)
        brand = QHBoxLayout()
        brand.setSpacing(12)
        logo = QLabel()
        logo.setPixmap(QPixmap(str(ASSETS / "icon.png")).scaled(
            54, 54, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        brand.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(Label("Rapier Desk", "brand"))
        names.addWidget(Label("Bee Sid's research desk"))
        brand.addLayout(names, 1)
        side.addLayout(brand)
        side.addSpacing(16)
        side.addWidget(Label("DESK", "eyebrow"))
        self.nav = QButtonGroup(self)
        for index, text in enumerate(("◉   Reports", "▶   New backtest")):
            button = QPushButton(text)
            button.setObjectName("nav")
            button.setCheckable(True)
            self.nav.addButton(button, index)
            side.addWidget(button)
        self.nav.button(0).clicked.connect(self.OpenReports)
        self.nav.button(1).clicked.connect(lambda: self.Show(1))
        side.addSpacing(12)
        side.addWidget(Label("SAVED RUNS", "eyebrow"))
        self.report_list = QListWidget()
        self.report_list.setItemDelegate(SlotDelegate(self.report_list))
        self.report_list.viewport().setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.report_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_list.currentRowChanged.connect(self.ShowReport)
        side.addWidget(self.report_list, 1)
        folder = QPushButton("↗   Open runs folder")
        folder.clicked.connect(self.OpenRuns)
        side.addWidget(folder)
        side.addWidget(Label("Research only · never places orders"))
        return sidebar

    def MakeOverview(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        area = QVBoxLayout(page)
        area.setContentsMargins(36, 28, 36, 32)
        area.setSpacing(16)
        area.addWidget(Label("BACKTEST ARCHIVE  ·  NQ FUTURES", "eyebrow"))
        self.report_title = Label("Know your numbers.", "title")
        area.addWidget(self.report_title)
        self.report_hint = Label("Choose a saved run on the left.")
        area.addWidget(self.report_hint)

        cards = QGridLayout()
        cards.setSpacing(12)
        self.stats: list[tuple[QLabel, QLabel]] = []
        for column, heading in enumerate(("NET P&L", "WIN RATE", "MAX DRAWDOWN", "TRADES")):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 14, 18, 14)
            box.addWidget(Label(heading, "eyebrow"))
            number = Label("—", "number")
            note = Label("")
            box.addWidget(number)
            box.addWidget(note)
            self.stats.append((number, note))
            cards.addWidget(card, 0, column)
        area.addLayout(cards)

        chart_panel, chart_layout = Panel("CLOSE-MARKED EQUITY  ·  INTRABAR DRAWDOWN", "Equity curve")
        self.chart = QLabel("Select a run to see its equity curve.")
        self.chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart.setMinimumHeight(260)
        self.chart.setStyleSheet(f"background: #ffffff; color: {NAVY}; border-radius: 10px; padding: 10px;")
        chart_layout.addWidget(self.chart)
        area.addWidget(chart_panel)

        goals_panel, goals_layout = Panel("NO PRETTY NUMBERS", "Goal check")
        self.goals = Label("—")
        self.goals.setTextFormat(Qt.TextFormat.RichText)
        goals_layout.addWidget(self.goals)
        area.addWidget(goals_panel)

        trades_panel, trades_layout = Panel("NEWEST FIRST", "Recent trades")
        self.trades = QTableWidget(0, 5)
        self.trades.setHorizontalHeaderLabels(["ENTRY (ET)", "BOOK", "SIDE", "P&L", "EXIT"])
        self.trades.horizontalHeader().setStretchLastSection(True)
        self.trades.verticalHeader().setVisible(False)
        self.trades.setAlternatingRowColors(True)
        self.trades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.trades.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.trades.setMinimumHeight(330)
        trades_layout.addWidget(self.trades)
        area.addWidget(trades_panel)
        area.addWidget(Label("Historical simulations are not live results or a guarantee of future performance."))
        scroll.setWidget(page)
        return scroll

    def MakeRunner(self) -> QWidget:
        page = QWidget()
        area = QVBoxLayout(page)
        area.setContentsMargins(40, 30, 40, 32)
        area.setSpacing(16)
        area.addWidget(Label("WORKBENCH  ·  SAFE SIMULATION", "eyebrow"))
        area.addWidget(Label("Run the tape.", "title"))
        area.addWidget(Label("Pick a period and a clock, name the run, and press run. "
                             "This only runs the backtester; it can never place orders."))
        panel, layout = Panel("SETTINGS", "New backtest")
        form = QFormLayout()
        form.setSpacing(14)
        self.run_name = QLineEdit()
        self.run_name.setMaxLength(60)
        self.run_name.setPlaceholderText("Latest Run  (type a name to keep this run)")
        form.addRow("Run name", self.run_name)
        self.start = QLineEdit("2025-07-26")
        self.start.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Start date", self.start)
        self.end = QLineEdit()
        self.end.setPlaceholderText("YYYY-MM-DD  (blank = up to the latest data)")
        form.addRow("End date", self.end)
        self.base = Choice(("1h  ·  swing and hourly books", "1h"), ("5m  ·  adds the 5m scalp book", "5m"),
                           ("1m  ·  adds the teacher 1m book", "1m"))
        form.addRow("Execution clock", self.base)
        self.mode = Choice(("As configured", "config"), ("Prop  ·  flat every day", "prop"),
                           ("Swing  ·  may hold overnight", "swing"))
        form.addRow("Risk mode", self.mode)
        self.source = Choice(("Yahoo", "yahoo"), ("IBKR history (from rapier ibkr-backfill)", "ibkr"))
        form.addRow("Market data", self.source)
        self.cached = QCheckBox("Reuse saved market data (skip re-downloading)")
        self.cached.setChecked(True)
        form.addRow("", self.cached)
        layout.addLayout(form)
        self.launch = QPushButton("▶   Run backtest")
        self.launch.setObjectName("primary")
        self.launch.clicked.connect(self.RunBacktest)
        layout.addWidget(self.launch)
        area.addWidget(panel)
        self.status = Label("Ready. Saved runs open without any market data.")
        area.addWidget(self.status)
        area.addWidget(Label("The first run downloads market data from Yahoo, which keeps only recent 1m and 5m "
                             "history. Leave the name blank to overwrite “Latest Run”."))
        area.addStretch()
        return page

    def Show(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.nav.button(index).setChecked(True)

    def OpenReports(self) -> None:
        self.Refresh()
        self.Show(0)

    def OpenRuns(self) -> None:
        self.paths.runs.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.runs)))

    def Refresh(self, select: str | None = None) -> None:
        row = self.report_list.currentRow()
        keep = select or (self.reports[row].name if 0 <= row < len(self.reports) else None)
        self.reports = LoadReports(self.paths.runs, self.paths.samples)
        self.report_list.blockSignals(True)
        self.report_list.clear()
        for report in self.reports:
            item = QListWidgetItem(report.title)
            item.setData(Qt.ItemDataRole.UserRole, report.dates)
            self.report_list.addItem(item)
        self.report_list.blockSignals(False)
        if not self.reports:
            self.report_hint.setText("No saved runs yet. Start one from New backtest.")
            return
        names = [report.name for report in self.reports]
        self.report_list.setCurrentRow(names.index(keep) if keep in names else 0)

    def ShowReport(self, index: int) -> None:
        if not 0 <= index < len(self.reports):
            return
        report = self.reports[index]
        self.Show(0)
        self.report_title.setText(report.title)
        self.report_hint.setText("  ·  ".join(filter(None, (report.dates, "historical simulation, not live results"))))
        s = report.summary
        net = float(s.get("net_usd") or 0)
        values = (f"{'-' if net < 0 else ''}${abs(net):,.0f}", f"{float(s.get('win_rate') or 0):.0%}",
                  f"${float(s.get('max_dd_usd') or 0):,.0f}", str(s.get("trades", 0)))
        notes = ("After costs", "Of closed trades", "Intrabar worst", "Completed trades")
        for (number, note), value, caption in zip(self.stats, values, notes):
            number.setText(value)
            note.setText(caption)
        self.stats[0][0].setStyleSheet(f"color: {UP if net >= 0 else DOWN};")
        chart = QPixmap(str(report.folder / "equity.png"))
        if chart.isNull():
            self.chart.setText("No equity chart in this run.")
        else:
            self.chart.setPixmap(chart.scaledToWidth(760, Qt.TransformationMode.SmoothTransformation))
        self.goals.setText("<br>".join(
            f"<span style='color:{UP if met else SOFT}'>{'●' if met else '○'}</span>&nbsp; "
            f"{html.escape(str(goal))}: <b>{'met' if met else 'not met'}</b>" for goal, met in report.goals.items()))
        recent = list(reversed(report.trades[-12:]))
        self.trades.setRowCount(len(recent))
        for row, trade in enumerate(recent):
            pnl = float(trade.get("pnl") or 0)
            values = ((trade.get("entry_time") or "")[:16], trade.get("book") or "",
                      "LONG" if trade.get("side") == "1" else "SHORT",
                      f"{'-' if pnl < 0 else ''}${abs(pnl):,.2f}", trade.get("exit_reason") or "")
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 3:
                    cell.setForeground(QColor(UP if pnl >= 0 else DOWN))
                self.trades.setItem(row, col, cell)
        self.trades.resizeColumnsToContents()
        self.trades.horizontalHeader().setStretchLastSection(True)

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
        self.pending = folder
        self.launch.setEnabled(False)
        self.status.setText(f"Running “{title}”… you can keep browsing saved runs meanwhile.")
        self.worker = BacktestWorker(args, staging, out, self.paths.data)
        self.worker.completed.connect(self.FinishBacktest)
        self.worker.start()

    def FinishBacktest(self, ok: bool, message: str) -> None:
        self.launch.setEnabled(True)
        self.status.setText(message)
        if ok:
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
    app.setApplicationName("Rapier Desk")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(QIcon(str(ASSETS / "icon.png")))
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) if getattr(sys, "frozen", False) else None
    user_data = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericDataLocation))
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

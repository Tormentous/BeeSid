"""Native, read-mostly desktop dashboard for Rapier reports and backtests."""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFormLayout,
                               QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

from .desktop_data import BacktestArgs, LoadReports, Report


STYLE = """
QWidget { background: #0a1220; color: #e9f3f5; font-family: 'Segoe UI', 'DejaVu Sans', sans-serif; font-size: 13px; }
QLabel { background: transparent; }
QFrame#side { background: #101f31; border-right: 1px solid #284053; }
QFrame#card, QFrame#panel { background: #14283a; border: 1px solid #284659; border-radius: 14px; }
QLabel#eyebrow { color: #64d9ce; font-size: 11px; font-weight: 800; letter-spacing: 2px; }
QLabel#title { color: #ffffff; font-size: 32px; font-weight: 800; }
QLabel#number { font-size: 26px; font-weight: 800; }
QLabel#muted { color: #99afbe; }
QPushButton { background: #1b3547; color: #eff9f8; border: 1px solid #37576a; border-radius: 8px; padding: 10px 16px; font-weight: 700; }
QPushButton:hover { background: #295469; border-color: #68d9cf; }
QPushButton:disabled { color: #7b929f; background: #162939; }
QPushButton#primary { background: #6adbcf; color: #091a25; border: 0; font-weight: 800; }
QPushButton#primary:hover { background: #a0f2df; }
QListWidget, QLineEdit, QComboBox, QTextEdit, QTableWidget { background: #0e1d2d; border: 1px solid #304b5e; border-radius: 8px; padding: 6px; selection-background-color: #286777; }
QListWidget::item { padding: 10px; border-radius: 6px; }
QListWidget::item:selected { background: #245b68; color: #ffffff; }
QHeaderView::section { background: #1c3a4a; color: #aeeae5; padding: 8px; border: 0; }
QScrollArea { border: 0; }
QScrollBar:vertical { background: #101f31; width: 9px; }
QScrollBar::handle:vertical { background: #3b6978; border-radius: 4px; min-height: 25px; }
QScrollBar:horizontal { background: #101f31; height: 9px; }
QScrollBar::handle:horizontal { background: #3b6978; border-radius: 4px; min-width: 25px; }
QCheckBox { spacing: 8px; }
"""


def Label(text: str, kind: str = "muted") -> QLabel:
    label = QLabel(text)
    label.setObjectName(kind)
    label.setWordWrap(True)
    return label


def Panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(12)
    return frame, layout


class BacktestWorker(QThread):
    completed = Signal(str)

    def __init__(self, args: list[str]):
        super().__init__()
        self.args = args

    def run(self) -> None:
        try:
            from .cli import Main as CliMain

            with redirect_stdout(StringIO()):
                CliMain(self.args)
        except (Exception, SystemExit) as exc:
            self.completed.emit(f"Backtest failed: {exc}")
        else:
            self.completed.emit("Backtest complete. Open 'latest' to see the new report.")


class Desk(QMainWindow):
    def __init__(self, root: Path):
        super().__init__()
        self.root = root
        self.worker: BacktestWorker | None = None
        self.reports: list[Report] = []
        self.setWindowTitle("Rapier Desk | Research cockpit")
        self.resize(1180, 780)
        self.setMinimumSize(900, 650)

        body = QWidget()
        self.setCentralWidget(body)
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("side")
        sidebar.setFixedWidth(255)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 24)
        side.setSpacing(14)
        side.addWidget(Label("◈  RAPIER / DESK", "eyebrow"))
        side.addWidget(Label("The trading\nresearch cockpit", "muted"))
        side.addSpacing(25)
        self.overview_button = QPushButton("◉  REPORTS")
        self.overview_button.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        side.addWidget(self.overview_button)
        self.run_button = QPushButton("➜  NEW BACKTEST")
        self.run_button.clicked.connect(lambda: self.pages.setCurrentIndex(1))
        side.addWidget(self.run_button)
        side.addSpacing(22)
        side.addWidget(Label("SAVED RUNS", "eyebrow"))
        self.report_list = QListWidget()
        self.report_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.report_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_list.currentRowChanged.connect(self.ShowReport)
        side.addWidget(self.report_list, 1)
        refresh = QPushButton("↻  Refresh reports")
        refresh.clicked.connect(self.Refresh)
        side.addWidget(refresh)
        side.addWidget(Label("RESEARCH ONLY  ·  No live orders", "eyebrow"))
        columns.addWidget(sidebar)

        self.pages = QStackedWidget()
        columns.addWidget(self.pages, 1)
        self.pages.addWidget(self.MakeOverview())
        self.pages.addWidget(self.MakeRunner())
        self.Refresh()

    def MakeOverview(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        area = QVBoxLayout(page)
        area.setContentsMargins(38, 30, 38, 32)
        area.setSpacing(18)
        area.addWidget(Label("BACKTEST ARCHIVE  /  NQ FUTURES", "eyebrow"))
        area.addWidget(Label("Know your numbers.", "title"))
        self.report_hint = Label("Choose a saved run on the left.")
        area.addWidget(self.report_hint)

        cards = QGridLayout()
        cards.setSpacing(12)
        self.stats: list[tuple[QLabel, QLabel]] = []
        for index, heading in enumerate(("NET P&L", "WIN RATE", "MAX DRAWDOWN", "TRADES")):
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(20, 16, 20, 16)
            box.addWidget(Label(heading, "eyebrow"))
            number = Label("—", "number")
            box.addWidget(number)
            note = Label("Saved backtest")
            box.addWidget(note)
            self.stats.append((number, note))
            cards.addWidget(card, index // 2, index % 2)
        area.addLayout(cards)

        chart_panel, chart_layout = Panel()
        chart_layout.addWidget(Label("EQUITY CURVE  /  INTRABAR DRAWDOWN", "eyebrow"))
        self.chart = QLabel("Select a report to see its equity curve.")
        self.chart.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart.setMinimumHeight(250)
        self.chart.setStyleSheet("background: #ffffff; color: #244054; border-radius: 8px; padding: 12px;")
        chart_layout.addWidget(self.chart)
        area.addWidget(chart_panel)

        goals_panel, goals_layout = Panel()
        goals_layout.addWidget(Label("GOAL CHECK  /  NO PRETTY NUMBERS", "eyebrow"))
        self.goals = Label("—")
        goals_layout.addWidget(self.goals)
        area.addWidget(goals_panel)

        trades_panel, trades_layout = Panel()
        trades_layout.addWidget(Label("RECENT TRADES", "eyebrow"))
        self.trades = QTableWidget(0, 5)
        self.trades.setHorizontalHeaderLabels(["ENTRY (ET)", "BOOK", "SIDE", "P&L", "EXIT"])
        self.trades.horizontalHeader().setStretchLastSection(True)
        self.trades.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.trades.setMinimumHeight(245)
        trades_layout.addWidget(self.trades)
        area.addWidget(trades_panel)
        area.addWidget(Label("Historical simulations are not live results or a guarantee of future performance."))
        scroll.setWidget(page)
        return scroll

    def MakeRunner(self) -> QWidget:
        page = QWidget()
        area = QVBoxLayout(page)
        area.setContentsMargins(45, 35, 45, 35)
        area.setSpacing(18)
        area.addWidget(Label("WORKBENCH  /  SAFE SIMULATION", "eyebrow"))
        area.addWidget(Label("Run the tape.", "title"))
        area.addWidget(Label("Choose a date range and execution clock. This only runs the backtester; it cannot place orders."))
        panel, layout = Panel()
        form = QFormLayout()
        form.setSpacing(15)
        self.start = QLineEdit("2025-07-26")
        self.start.setPlaceholderText("YYYY-MM-DD")
        form.addRow("Start date", self.start)
        self.end = QLineEdit()
        self.end.setPlaceholderText("YYYY-MM-DD (leave blank for latest)")
        form.addRow("End date", self.end)
        self.base = QComboBox()
        self.base.addItems(["1h", "5m", "1m"])
        form.addRow("Execution clock", self.base)
        self.mode = QComboBox()
        self.mode.addItems(["config", "prop", "swing"])
        form.addRow("Risk mode", self.mode)
        self.source = QComboBox()
        self.source.addItems(["yahoo", "ibkr"])
        form.addRow("Market data", self.source)
        self.cached = QCheckBox("Use local cache only (no data download)")
        self.cached.setChecked(True)
        form.addRow("", self.cached)
        layout.addLayout(form)
        self.launch = QPushButton("▶  RUN BACKTEST")
        self.launch.setObjectName("primary")
        self.launch.clicked.connect(self.RunBacktest)
        layout.addWidget(self.launch)
        area.addWidget(panel)
        self.status = Label("Ready. Saved reports work without market-data access.")
        area.addWidget(self.status)
        area.addWidget(Label("1m / 5m need local history; Yahoo's shorter interval history is limited. No tuning or live trading here."))
        area.addStretch()
        return page

    def Refresh(self) -> None:
        previous = self.report_list.currentItem()
        selected = previous.text() if previous else None
        self.reports = LoadReports(self.root / "results")
        self.report_list.blockSignals(True)
        self.report_list.clear()
        for report in self.reports:
            self.report_list.addItem(report.name)
        self.report_list.blockSignals(False)
        if self.reports:
            names = [report.name for report in self.reports]
            self.report_list.setCurrentRow(names.index(selected) if selected in names else 0)
        else:
            self.report_hint.setText("No saved reports yet. Run a backtest to create results/latest.")

    def ShowReport(self, index: int) -> None:
        if index < 0 or index >= len(self.reports):
            return
        report = self.reports[index]
        self.pages.setCurrentIndex(0)
        self.report_hint.setText(f"{report.name}  ·  historical simulation, not live performance")
        s = report.summary
        values = (f"${s.get('net_usd', 0):,.0f}", f"{s.get('win_rate', 0):.0%}",
                  f"${s.get('max_dd_usd', 0):,.0f}", str(s.get("trades", 0)))
        notes = ("After costs", "Of closed trades", "Intrabar worst", "Completed trades")
        for (number, note), value, caption in zip(self.stats, values, notes):
            number.setText(value)
            note.setText(caption)
        self.stats[0][0].setStyleSheet(f"color: {'#71e2bb' if s.get('net_usd', 0) >= 0 else '#ff948a'};")
        chart = QPixmap(str(report.folder / "equity.png"))
        self.chart.setPixmap(chart.scaledToWidth(750, Qt.TransformationMode.SmoothTransformation) if not chart.isNull() else QPixmap())
        if chart.isNull():
            self.chart.setText("No equity chart in this report.")
        self.goals.setText("\n".join(f"{'●' if met else '○'}  {goal}: {'met' if met else 'not met'}"
                                      for goal, met in report.goals.items()))
        recent = list(reversed(report.trades[-12:]))
        self.trades.setRowCount(len(recent))
        for row, trade in enumerate(recent):
            side = "LONG" if trade.get("side") == "1" else "SHORT"
            values = (trade.get("entry_time", "")[:16], trade.get("book", ""), side,
                      f"${float(trade.get('pnl') or 0):,.2f}", trade.get("exit_reason", ""))
            for col, value in enumerate(values):
                cell = QTableWidgetItem(value)
                if col == 3:
                    cell.setForeground(QColor("#71e2bb" if float(trade.get("pnl") or 0) >= 0 else "#ff948a"))
                self.trades.setItem(row, col, cell)
        self.trades.resizeColumnsToContents()

    def RunBacktest(self) -> None:
        try:
            args = BacktestArgs(self.start.text().strip(), self.end.text().strip(),
                                self.base.currentText(), self.mode.currentText(),
                                self.source.currentText(), self.cached.isChecked())
        except ValueError as exc:
            QMessageBox.warning(self, "Check the dates", str(exc))
            return
        self.launch.setEnabled(False)
        self.status.setText("Running backtest in the background. The dashboard will stay responsive…")
        self.worker = BacktestWorker(args)
        self.worker.completed.connect(self.FinishBacktest)
        self.worker.start()

    def FinishBacktest(self, message: str) -> None:
        self.launch.setEnabled(True)
        self.status.setText(message)
        self.Refresh()

    def closeEvent(self, event) -> None:
        if self.worker is not None and self.worker.isRunning():
            QMessageBox.information(self, "Backtest running", "Wait for the backtest to finish before closing.")
            event.ignore()
        else:
            event.accept()


def Main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    root = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent
    window = Desk(root)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    Main()

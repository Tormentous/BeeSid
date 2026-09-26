"""Checks the desktop helpers: saved runs, readable run names, where the exe keeps files, and safe backtest commands."""

import json
import os

import pytest

from rapier.desktop_data import (AppPaths, BacktestArgs, DisplayName, EngineCheck, EquityCurve, GoalLabel, GoalScore,
                                 LoadReports, Money, NiceStep, Paths, Publish, RunFolder, Staging)

HEADING = "# Prop Firm Rapier | 2025-07-26 -> today | base 1h | prop | yahoo"


def WriteRun(folder, net=120, heading=HEADING):
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps({"summary": {"net_usd": net}, "goals": {"1R": True}}))
    (folder / "trades.csv").write_text(f"book,pnl\note-1h,{net}\n")
    (folder / "summary.md").write_text(heading + "\n")


def TestReportsLoadWithoutMarketData(tmp_path):
    WriteRun(tmp_path / "results" / "saved")
    (tmp_path / "results" / "broken").mkdir()
    WriteRun(tmp_path / "results" / ".saved.partial")
    try:
        (tmp_path / "results" / "outside").symlink_to(tmp_path / "results" / "saved", target_is_directory=True)
    except OSError:
        pass  # Windows may not permit symlinks without Developer Mode.
    reports = LoadReports(tmp_path / "results")
    assert [r.name for r in reports] == ["saved"]
    assert reports[0].trades[0]["pnl"] == "120"


def TestFinishedRunReplacesTheOldOneInOneStep(tmp_path):
    out = tmp_path / "runs" / "My Run"
    WriteRun(out, net=1)
    (out / "equity.png").write_bytes(b"old chart")
    staging = Staging(out)
    assert staging.name == ".My Run.partial"
    WriteRun(staging, net=2)
    Publish(staging, out)
    assert not staging.exists() and not (out / "equity.png").exists()
    assert json.loads((out / "summary.json").read_text())["summary"]["net_usd"] == 2


def TestSavedRunsGetReadableNames():
    assert DisplayName("main_2025-07-26_to_2026-09-24") == ("Main Backtest", "Jul 26, 2025 – Sep 24, 2026")
    assert DisplayName("oos_2024-06-15_to_2025-07-25") == ("Out-of-Sample Test", "Jun 15, 2024 – Jul 25, 2025")
    assert DisplayName("recent_1m_all_books_2026-08-24_to_2026-09-24") == ("Recent 1m All Books",
                                                                         "Aug 24 – Sep 24, 2026")
    assert DisplayName("variant_swing_overnight", HEADING) == ("Variant Swing Overnight", "From Jul 26, 2025")
    assert DisplayName("latest") == ("Latest Run", "")
    assert DisplayName("ibkr_1m") == ("IBKR 1m", "")
    assert DisplayName("My June Test") == ("My June Test", "")
    assert DisplayName("odd_2025-13-01_to_2026-01-01")[1] == ""


def TestEngineCheckWritesAFullReport(tmp_path):
    assert EngineCheck(tmp_path) > 0
    assert {p.name for p in tmp_path.iterdir()} >= {"summary.json", "summary.md", "trades.csv", "equity.png"}


def TestEquityCurveFollowsExitOrder():
    trades = [{"exit_time": "2025-07-29 15:00:00-04:00", "pnl": "10"},
              {"exit_time": "2025-07-29 11:00:00-04:00", "pnl": "-4"}]
    assert EquityCurve(trades) == [("2025-07-29", -4.0, -4.0), ("2025-07-29", 10.0, 6.0)]
    assert EquityCurve([]) == []


def TestGoalsAndMoneyReadNicely():
    assert GoalScore({"win rate >= 75%": False, "every trade planned >= 1R": True}) == (1, 2)
    assert GoalLabel("win rate >= 75%") == "Win rate ≥ 75%"
    assert Money(3048.2, True) == "+$3,048"
    assert Money(-365.7) == "-$366"
    assert Money(0.3, True) == "$0"


def TestChartGridlinesUseRoundSteps():
    # just above and just below 4 x $1,000 must both give $1,000 steps, not jump to $2,000
    assert NiceStep(4001) == 1000
    assert NiceStep(3999) == 1000
    assert NiceStep(430) == 100
    assert NiceStep(9000) == 2500


def TestSavedRunsComeBeforeBundledSamples(tmp_path):
    WriteRun(tmp_path / "runs" / "My June Test", net=5)
    WriteRun(tmp_path / "samples" / "main_2025-07-26_to_2026-09-24")
    WriteRun(tmp_path / "samples" / "My June Test", net=99)
    reports = LoadReports(tmp_path / "runs", tmp_path / "samples")
    assert [r.title for r in reports] == ["My June Test", "Main Backtest"]
    assert reports[0].summary["net_usd"] == 5


def TestRunNamesBecomeSafeFolders():
    assert RunFolder("  My June   Test ") == "My June Test"
    assert RunFolder('Q3: "best" <try>/2?') == "Q3 best try 2"
    assert RunFolder("con") == "con Run"
    assert RunFolder(" .. ") == "latest"
    assert RunFolder("Latest Run") == "latest"
    assert len(RunFolder("x" * 200)) == 60


def TestExeKeepsRunsOutsideItsTemporaryFolder(tmp_path):
    source = AppPaths(tmp_path / "repo", None, tmp_path / "home")
    assert source == Paths(tmp_path / "repo" / "results", None, None)
    exe = AppPaths(tmp_path / "repo", tmp_path / "unpacked", tmp_path / "home")
    assert exe.runs == tmp_path / "home" / "RapierDesk" / "results"
    assert exe.data == tmp_path / "home" / "RapierDesk" / "data"
    assert exe.samples == tmp_path / "unpacked" / "results"


def TestBacktestArgsCannotStartTrading(tmp_path):
    out = tmp_path / "runs" / "My Run"
    args = BacktestArgs("2025-07-26", "", "5m", "prop", "yahoo", True, out)
    assert args == ["backtest", "--start", "2025-07-26", "--base", "5m", "--mode", "prop",
                    "--source", "yahoo", "--out", str(out), "--cached"]
    assert "--arm" not in args


def TestBacktestRejectsBadDatesAndOptions(tmp_path):
    for values in (("yesterday", "", "1h", "prop", "yahoo", True),
                   ("2025-07-26", "2025-07-25", "1h", "prop", "yahoo", True),
                   ("2025-07-26", "", "4h", "prop", "yahoo", True),
                   ("2025-07-26", "", "1h", "prop", "unsafe", True)):
        with pytest.raises(ValueError):
            BacktestArgs(*values, tmp_path / "latest")


def TestDeskShowsRunsAsSaveSlots(tmp_path, monkeypatch):
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    from PySide6.QtWidgets import QApplication

    from rapier.desktop import Desk

    WriteRun(tmp_path / "runs" / "oos_2024-06-15_to_2025-07-25")
    app = QApplication.instance() or QApplication([])
    desk = Desk(Paths(tmp_path / "runs", None, None))
    assert [card.report.title for card in desk.slot_cards] == ["Out-of-Sample Test"]
    desk.slot_cards[0].clicked.emit()
    assert desk.pages.currentIndex() == 2
    assert desk.report_title.text() == "Out-of-Sample Test"
    assert desk.stats[0][0].text() == "+$120"
    desk.close()
    app.processEvents()

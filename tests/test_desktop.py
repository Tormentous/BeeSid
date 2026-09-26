"""Desktop report loading and safe backtest command tests."""

import json

import pytest

from rapier.desktop_data import BacktestArgs, LoadReports


def TestReportsLoadWithoutMarketData(tmp_path):
    folder = tmp_path / "results" / "saved"
    folder.mkdir(parents=True)
    (folder / "summary.json").write_text(json.dumps({"summary": {"net_usd": 120}, "goals": {"1R": True}}))
    (folder / "trades.csv").write_text("book,pnl\note-1h,120\n")
    (tmp_path / "results" / "broken").mkdir()
    try:
        (tmp_path / "results" / "outside").symlink_to(folder, target_is_directory=True)
    except OSError:
        pass  # Windows may not permit symlinks without Developer Mode.
    reports = LoadReports(tmp_path / "results")
    assert [r.name for r in reports] == ["saved"]
    assert reports[0].trades[0]["pnl"] == "120"


def TestBacktestArgsCannotStartTrading():
    args = BacktestArgs("2025-07-26", "", "5m", "prop", "yahoo", True)
    assert args == ["backtest", "--start", "2025-07-26", "--base", "5m", "--mode", "prop",
                    "--source", "yahoo", "--out", "results/latest", "--cached"]
    assert "--arm" not in args


def TestBacktestRejectsBadDatesAndOptions():
    for values in (("yesterday", "", "1h", "prop", "yahoo", True),
                   ("2025-07-26", "2025-07-25", "1h", "prop", "yahoo", True),
                   ("2025-07-26", "", "4h", "prop", "yahoo", True),
                   ("2025-07-26", "", "1h", "prop", "unsafe", True)):
        with pytest.raises(ValueError):
            BacktestArgs(*values)

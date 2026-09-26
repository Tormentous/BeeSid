"""Load local backtest reports and validate desktop backtest requests."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Report:
    name: str
    folder: Path
    summary: dict
    goals: dict
    trades: list[dict]


def LoadReports(root: Path) -> list[Report]:
    reports = []
    if not root.is_dir():
        return reports
    for folder in root.iterdir():
        if not folder.is_dir() or folder.is_symlink():
            continue
        try:
            data = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
            with (folder / "trades.csv").open(encoding="utf-8", newline="") as file:
                trades = list(csv.DictReader(file))
            if not isinstance(data["summary"], dict) or not isinstance(data["goals"], dict):
                continue
            reports.append(Report(folder.name, folder, data["summary"], data["goals"], trades))
        except (OSError, ValueError, KeyError, UnicodeError):
            continue
    return sorted(reports, key=lambda r: (r.name == "latest", r.name), reverse=True)


def BacktestArgs(start: str, end: str, base: str, mode: str, source: str, cached: bool) -> list[str]:
    begin = date.fromisoformat(start)
    if end and date.fromisoformat(end) < begin:
        raise ValueError("End date must be on or after start date.")
    if base not in ("1h", "5m", "1m") or mode not in ("config", "prop", "swing"):
        raise ValueError("Invalid timeframe or mode.")
    if source not in ("yahoo", "ibkr"):
        raise ValueError("Invalid data source.")
    args = ["backtest", "--start", start, "--base", base, "--mode", mode,
            "--source", source, "--out", "results/latest"]
    if end:
        args.extend(("--end", end))
    if cached:
        args.append("--cached")
    return args

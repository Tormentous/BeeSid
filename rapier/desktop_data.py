"""Saved backtest runs for the desktop app: where they live, readable names, and safe backtest requests."""

from __future__ import annotations

import csv
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LATEST = "latest"
_MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
_TITLES = {"latest": "Latest Run", "main": "Main Backtest", "oos": "Out-of-Sample Test"}
_WORDS = {"oos": "Out-of-Sample", "ibkr": "IBKR"}
_FOLDER_DATES = re.compile(r"(?:^|_)(\d{4}-\d{2}-\d{2})_to_(\d{4}-\d{2}-\d{2})$")
_HEADING_DATES = re.compile(r"\| (\d{4}-\d{2}-\d{2}) -> (\S+) \|")
_TIMEFRAME = re.compile(r"\d+[mhdw]")
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


@dataclass(frozen=True)
class Report:
    name: str
    title: str
    dates: str
    folder: Path
    summary: dict
    goals: dict
    trades: list[dict]


@dataclass(frozen=True)
class Paths:
    runs: Path
    samples: Path | None
    data: Path | None


def AppPaths(repo: Path, bundle: Path | None, user_data: Path) -> Paths:
    """Runs live in the repository when started from source and in the user's data folder when packaged."""
    if bundle is None:
        return Paths(repo / "results", None, None)
    # A one-file exe unpacks into a temporary folder that is deleted on exit, so saved work must live elsewhere.
    home = user_data / "RapierDesk"
    return Paths(home / "results", bundle / "results", home / "data")


def _Day(day: date, year: bool) -> str:
    return f"{_MONTHS[day.month - 1]} {day.day}" + (f", {day.year}" if year else "")


def _Span(start: str, end: str) -> str:
    try:
        first = date.fromisoformat(start)
        last = None if end == "today" else date.fromisoformat(end)
    except ValueError:
        return ""
    if last is None:
        return f"From {_Day(first, True)}"
    return f"{_Day(first, first.year != last.year)} – {_Day(last, True)}"


def DisplayName(folder: str, heading: str = "") -> tuple[str, str]:
    """Readable title and date range for a run folder such as ``oos_2024-06-15_to_2025-07-25``.

    ``heading`` is the first line of the run's summary.md; it supplies the dates when the folder name has none.
    """
    stem, dates = folder, ""
    found = _FOLDER_DATES.search(folder)
    if found and (dates := _Span(found[1], found[2])):
        stem = folder[:found.start()]
    elif found := _HEADING_DATES.search(heading):
        dates = _Span(found[1], found[2])
    if "_" not in stem and not stem.islower():
        return stem or "Backtest", dates
    words = [_WORDS.get(w, w if _TIMEFRAME.fullmatch(w) else w[:1].upper() + w[1:]) for w in stem.split("_") if w]
    return _TITLES.get(stem) or " ".join(words) or "Backtest", dates


def RunFolder(name: str) -> str:
    """Folder for a user-named run: capitals and spaces are kept, characters Windows forbids are dropped."""
    clean = " ".join(_UNSAFE.sub(" ", name).split())[:60].strip(" .")
    if not clean or clean.casefold() in (LATEST, "latest run"):
        return LATEST
    return f"{clean} Run" if clean.split(".")[0].upper() in _RESERVED else clean


def Staging(out: Path) -> Path:
    """Hidden folder a run is written to first, so a failed run never replaces or half-fills a saved one."""
    return out.with_name(f".{out.name}.partial")


def Publish(staging: Path, out: Path) -> None:
    if out.exists():
        shutil.rmtree(out)
    staging.rename(out)


def EngineCheck(folder: Path) -> int:
    """Run the real engine and report writer on made-up bars, so a packaged build can prove it works offline."""
    import numpy as np
    import pandas as pd

    from . import data as D
    from .backtest import BookConfig, Market, RiskConfig, Run
    from .report import Write
    from .strategy import SetupParams

    rng = np.random.default_rng(5)
    idx = pd.date_range("2025-01-06 18:00", periods=4000, freq="1h", tz=D.TZ)
    idx = idx[(idx.hour != 17) & (idx.dayofweek < 5)][:2000]
    close = 20000 + np.cumsum(rng.normal(0.5, 25, len(idx)))
    open_ = np.r_[close[0], close[:-1]]
    bars = pd.DataFrame({"open": open_, "high": np.maximum(open_, close) + rng.uniform(0, 15, len(idx)),
                         "low": np.minimum(open_, close) - rng.uniform(0, 15, len(idx)), "close": close,
                         "volume": 1000.0}, index=idx)
    book = BookConfig("ote-1h", "1h", SetupParams(k=2, min_leg_atr=1.0), bias_tfs=())
    result = Run(Market.From1h(bars), (book,), RiskConfig(flatten_eod=False, daily_loss_limit=1e9, dd_throttle=None))
    Write(result, folder, "Rapier Desk self-test (synthetic bars)")
    return len(result.trades)


def _Load(folder: Path) -> Report | None:
    try:
        data = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
        with (folder / "trades.csv").open(encoding="utf-8", newline="") as file:
            trades = list(csv.DictReader(file))
        summary, goals = data["summary"], data["goals"]
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return None
    if not isinstance(summary, dict) or not isinstance(goals, dict):
        return None
    try:
        with (folder / "summary.md").open(encoding="utf-8") as file:
            heading = file.readline()
    except (OSError, UnicodeError):
        heading = ""
    title, dates = DisplayName(folder.name, heading)
    return Report(folder.name, title, dates, folder, summary, goals, trades)


def LoadReports(runs: Path, samples: Path | None = None) -> list[Report]:
    """Saved runs (newest first), then bundled example runs; a saved run hides a sample with the same folder."""
    reports: dict[str, Report] = {}
    for root in (runs, samples):
        if root is None or not root.is_dir():
            continue
        loaded = []
        for folder in root.iterdir():
            if folder.name.startswith(".") or folder.is_symlink() or not folder.is_dir():
                continue
            if report := _Load(folder):
                # Minute buckets keep runs from one checkout or unpack in title order.
                loaded.append((-int((folder / "summary.json").stat().st_mtime // 60), report.title, report))
        for *_, report in sorted(loaded, key=lambda row: row[:2]):
            reports.setdefault(report.name, report)
    return list(reports.values())


def BacktestArgs(start: str, end: str, base: str, mode: str, source: str, cached: bool, out: Path) -> list[str]:
    try:
        begin = date.fromisoformat(start)
        finish = date.fromisoformat(end) if end else None
    except ValueError:
        raise ValueError("Dates must look like 2025-07-26 (year-month-day).") from None
    if finish and finish < begin:
        raise ValueError("End date must be on or after start date.")
    if base not in ("1h", "5m", "1m") or mode not in ("config", "prop", "swing"):
        raise ValueError("Invalid timeframe or mode.")
    if source not in ("yahoo", "ibkr"):
        raise ValueError("Invalid data source.")
    args = ["backtest", "--start", start, "--base", base, "--mode", mode, "--source", source, "--out", str(out)]
    if end:
        args.extend(("--end", end))
    if cached:
        args.append("--cached")
    return args

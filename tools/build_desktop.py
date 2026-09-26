"""Build the Bee Sid app as one double-click file (BeeSid.exe on Windows, BeeSid on Linux) and self-test it.

Run from the repository root after installing the desktop extras and PyInstaller:

    python -m pip install -e ".[desktop]" "pyinstaller>=6.10,<7"
    python tools/build_desktop.py

The example runs in results/ are packed into the file; results/latest is left out.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAME = "BeeSid"


def Samples() -> list[Path]:
    return sorted(p for p in (ROOT / "results").iterdir()
                  if p.is_dir() and p.name != "latest" and (p / "summary.json").exists())


def Build(samples: list[Path]) -> Path:
    import PyInstaller.__main__

    args = ["--noconfirm", "--clean", "--onefile", "--windowed", "--name", NAME,
            "--icon", str(ROOT / "rapier" / "assets" / "icon.ico"),
            "--collect-data", "rapier", "--collect-submodules", "rapier",
            # pandas imports tabulate only when writing summary.md tables, so PyInstaller cannot see it;
            # tabulate reads its version from package metadata, which pandas checks.
            "--hidden-import", "tabulate", "--copy-metadata", "tabulate",
            "--specpath", str(ROOT / "build"), "--workpath", str(ROOT / "build"),
            "--distpath", str(ROOT / "dist")]
    for folder in samples:
        args += ["--add-data", f"{folder}{os.pathsep}results/{folder.name}"]
    # The splash shows while the one-file app unpacks; PyInstaller needs Tk at build time to add it.
    if importlib.util.find_spec("tkinter"):
        args += ["--splash", str(ROOT / "rapier" / "assets" / "splash.png")]
    else:
        print("tkinter is not installed: building without the startup splash")
    PyInstaller.__main__.run([*args, str(ROOT / "desktop_main.py")])
    return ROOT / "dist" / (NAME + (".exe" if os.name == "nt" else ""))


def SelfTest(app: Path, samples: int) -> dict:
    env = dict(os.environ)
    if sys.platform.startswith("linux"):
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "self-test.json"
        started = time.monotonic()
        subprocess.run([str(app), "--self-test", str(out)], env=env, check=True, timeout=300)
        result = json.loads(out.read_text(encoding="utf-8"))
    result["seconds"] = round(time.monotonic() - started, 1)
    titles = result["reports"]
    if len(titles) < samples or any("_" in title for title in titles):
        raise SystemExit(f"self-test: expected {samples} readable example runs, got {titles}")
    if Path(result["runs"]).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise SystemExit(f"self-test: runs would be saved in the temporary unpack folder: {result['runs']}")
    report_files = {"summary.json", "summary.md", "trades.csv", "equity.png"}
    if result["engine_trades"] < 1 or not report_files <= set(result["report_files"]):
        raise SystemExit(f"self-test: the packaged engine could not write a full report: {result}")
    return result


if __name__ == "__main__":
    found = Samples()
    app = Build(found)
    report = SelfTest(app, len(found))
    print(json.dumps(report, indent=2))
    print(f"built {app} ({app.stat().st_size / 1e6:.0f} MB); self-test passed in {report['seconds']} s")

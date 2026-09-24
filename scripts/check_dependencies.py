#!/usr/bin/env python3
"""Detect score-transposition dependencies; never installs anything."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
from pathlib import Path

try:
    from .common import find_executable
except ImportError:
    from common import find_executable


COMMANDS = {
    "python": ["python3", "python"],
    "lilypond": ["lilypond"],
    "audiveris": ["audiveris"],
    "homr": ["homr"],
    "musescore": ["musescore4", "mscore", "musescore"],
    "pdfinfo": ["pdfinfo"],
    "pdftoppm": ["pdftoppm"],
}
VERSION_ARGS = {"pdfinfo": ["-v"], "pdftoppm": ["-v"]}


def version(executable: str) -> str | None:
    name = Path(executable).name
    try:
        result = subprocess.run([executable] + VERSION_ARGS.get(name, ["--version"]), capture_output=True, text=True, timeout=5)
        output = (result.stdout or result.stderr).strip().splitlines()
        return output[0][:240] if output else None
    except (OSError, subprocess.SubprocessError):
        return None


def collect(python_executable: str | None = None, only: list[str] | None = None) -> dict:
    selected = set(only or COMMANDS)
    commands = {}
    for name, candidates in COMMANDS.items():
        if name not in selected and not (name in {"pdfinfo", "pdftoppm"} and "poppler" in selected):
            continue
        path = find_executable(*candidates)
        commands[name] = {"available": bool(path), "path": path, "version": version(path) if path else None, "candidates": candidates}
    interpreter = python_executable or commands.get("python", {}).get("path") or shutil.which("python3") or shutil.which("python")
    return {"platform": platform.platform(), "python_executable": interpreter, "commands": commands}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--python", dest="python_executable")
    parser.add_argument("--only", nargs="+", choices=["python", "lilypond", "audiveris", "homr", "musescore", "poppler"])
    args = parser.parse_args()
    result = collect(args.python_executable, args.only)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Platform: {result['platform']}")
        for name, item in result["commands"].items():
            suffix = f" — {item['version']}" if item.get("version") else ""
            print(f"{name}: {'available' if item['available'] else 'missing'}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""One-time environment bootstrap with a persistent success marker."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from .check_dependencies import collect
except ImportError:
    from check_dependencies import collect


def missing_system(snapshot: dict) -> list[str]:
    commands = snapshot.get("commands", {})
    missing = []
    if not commands.get("python", {}).get("available"):
        missing.append("python")
    for name in ("audiveris", "musescore"):
        if not commands.get(name, {}).get("available"):
            missing.append(name)
    if not commands.get("pdfinfo", {}).get("available") or not commands.get("pdftoppm", {}).get("available"):
        missing.append("poppler")
    return missing


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-install", action="store_true", help="authorize installation of all missing system dependencies in one pass")
    parser.add_argument("--force", action="store_true", help="ignore a prior marker and intentionally reinitialize")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    skill_dir = Path(__file__).resolve().parents[1]
    marker = skill_dir / ".score-transposer-initialized"
    if marker.exists() and not args.force:
        result = {"status": "initialized", "marker": str(marker), "skipped_full_check": True}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else "score-transposer is already initialized; skipped full dependency check")
        return 0

    snapshot = collect()
    missing = missing_system(snapshot)
    if missing and not args.confirm_install:
        result = {"status": "authorization_required", "missing_system": missing, "reason": "These system dependencies are used for score recognition, digitization, transposition, and output. One authorization will install all of them.", "marker": str(marker)}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Missing system dependencies: {', '.join(missing)}\nOne installation authorization is required before installing them.")
        return 4

    install_report = None
    if missing:
        installer = skill_dir / "scripts" / "install_dependencies.py"
        install_result = subprocess.run([sys.executable, str(installer), "--confirm-install", "--only", *missing], capture_output=True, text=True, timeout=1200)
        install_report = {"requested": missing, "returncode": install_result.returncode, "output": (install_result.stdout + "\n" + install_result.stderr)[-4000:]}
        snapshot = collect()
        missing = missing_system(snapshot)
        if missing:
            result = {"status": "failed", "missing_system": missing, "install": install_report, "marker": str(marker)}
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Initialization failed; still missing: {', '.join(missing)}")
            return 3

    python_path = snapshot["commands"]["python"]["path"]
    if not python_path:
        result = {"status": "failed", "missing_system": ["python"], "marker": str(marker)}
        print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else "Initialization failed: Python is unavailable")
        return 3
    state = {"version": 3, "initialized_at": datetime.now(timezone.utc).isoformat(), "platform": snapshot["platform"], "python": str(python_path), "system_dependencies": snapshot, "optional_dependencies": {"lilypond": snapshot.get("commands", {}).get("lilypond", {}), "homr": snapshot.get("commands", {}).get("homr", {})}}
    marker.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = {"status": "initialized", "marker": str(marker), "system_dependencies": snapshot, "optional_dependencies": state["optional_dependencies"], "install": install_report}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"score-transposer initialized; marker written to {marker}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

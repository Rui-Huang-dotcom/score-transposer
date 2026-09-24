#!/usr/bin/env python3
"""Install selected system dependencies only after an explicit authorization guard."""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess


def commands_for(system: str) -> dict[str, list[str]]:
    if system == "Darwin":
        return {
            "python": ["brew", "install", "python"],
            "lilypond": ["brew", "install", "lilypond"],
            "audiveris": ["brew", "install", "audiveris"],
            "musescore": ["brew", "install", "--cask", "musescore"],
            "poppler": ["brew", "install", "poppler"],
        }
    if system == "Linux":
        return {
            "python": ["sudo", "apt-get", "install", "python3"],
            "lilypond": ["sudo", "apt-get", "install", "lilypond"],
            "audiveris": ["sudo", "apt-get", "install", "audiveris"],
            "musescore": ["sudo", "apt-get", "install", "musescore3"],
            "poppler": ["sudo", "apt-get", "install", "poppler-utils"],
        }
    if system == "Windows":
        return {
            "python": ["winget", "install", "--id", "Python.Python.3.12", "--exact"],
            "musescore": ["winget", "install", "--id", "MuseScore.MuseScore", "--exact"],
        }
    return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-install", action="store_true", help="required before any package-manager command runs")
    parser.add_argument("--only", nargs="+", choices=["python", "lilypond", "audiveris", "musescore", "poppler"], help="install only the named system dependencies")
    args = parser.parse_args()
    plan = commands_for(platform.system())
    selected = args.only or list(plan)
    print("Planned system dependency installation for", platform.system())
    for name in selected:
        if name in plan:
            print(" ", name + ":", " ".join(plan[name]))
    if not args.confirm_install:
        print("No changes made. Ask the user for one installation authorization, then re-run with --confirm-install.")
        return 0
    for name in selected:
        command = plan.get(name)
        if not command:
            print(f"Skipping {name}: no supported installer for {platform.system()}")
            continue
        if not shutil.which(command[0]):
            print(f"Skipping {name}: {command[0]} is unavailable")
            continue
        result = subprocess.run(command, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

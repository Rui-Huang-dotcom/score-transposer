#!/usr/bin/env python3
"""Render MusicXML with MuseScore or LilyPond, without pretending rendering is semantic conversion."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import find_executable


def render_musicxml(source: Path, output_pdf: Path) -> dict:
    executable = find_executable("musescore4", "mscore", "musescore")
    if not executable:
        return {"passed": False, "error": "MuseScore is not installed; it is required to engrave MusicXML to PDF"}
    output_pdf.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([executable, "-o", str(output_pdf), str(source)], capture_output=True, text=True, timeout=180)
    primary = {"passed": result.returncode == 0 and output_pdf.exists(), "tool": executable, "output": str(output_pdf), "returncode": result.returncode, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:]}
    if primary["passed"]:
        return primary
    fallback = render_musicxml_via_lilypond(source, output_pdf)
    return {"passed": fallback.get("passed", False), "tool": executable, "output": str(output_pdf), "returncode": result.returncode, "stdout": result.stdout[-2000:], "stderr": result.stderr[-2000:], "musescore": primary, "fallback": fallback}


def render_musicxml_via_lilypond(source: Path, output_pdf: Path) -> dict:
    """Use LilyPond's MusicXML importer only after MuseScore has failed."""
    importer = shutil.which("musicxml2ly")
    lilypond = shutil.which("lilypond")
    if not importer or not lilypond:
        return {"passed": False, "tool": "lilypond", "error": "musicxml2ly or lilypond is unavailable"}
    with tempfile.TemporaryDirectory(prefix="score-lilypond-") as temp:
        temp_dir = Path(temp)
        ly = temp_dir / "score.ly"
        converted = subprocess.run([importer, "--output", str(ly), str(source)], capture_output=True, text=True, timeout=180)
        if converted.returncode != 0 or not ly.exists():
            return {"passed": False, "tool": importer, "returncode": converted.returncode, "stdout": converted.stdout[-2000:], "stderr": converted.stderr[-2000:]}
        output_base = temp_dir / "score"
        rendered = subprocess.run([lilypond, "-o", str(output_base), str(ly)], capture_output=True, text=True, timeout=180)
        generated = output_base.with_suffix(".pdf")
        if rendered.returncode == 0 and generated.exists():
            output_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(generated, output_pdf)
        return {"passed": rendered.returncode == 0 and output_pdf.exists(), "tool": lilypond, "output": str(output_pdf), "returncode": rendered.returncode, "stdout": rendered.stdout[-2000:], "stderr": rendered.stderr[-2000:]}


def render_lilypond(source: Path, output_dir: Path) -> dict:
    executable = shutil.which("lilypond")
    if not executable:
        return {"passed": False, "error": "LilyPond is not installed; it is required to render .ly output"}
    output_dir.mkdir(parents=True, exist_ok=True)
    output_base = output_dir / source.stem
    result = subprocess.run([executable, "-o", str(output_base), str(source)], capture_output=True, text=True, timeout=180)
    output_pdf = output_base.with_suffix(".pdf")
    return {"passed": result.returncode == 0 and output_pdf.exists(), "tool": executable, "output": str(output_pdf), "returncode": result.returncode, "stderr": result.stderr[-2000:]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--musicxml")
    parser.add_argument("--pdf")
    parser.add_argument("--lilypond")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--output-pdf")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.musicxml:
        result = render_musicxml(Path(args.musicxml), Path(args.output_pdf) if args.output_pdf else Path(args.output_dir) / (Path(args.musicxml).stem + ".pdf"))
    elif args.lilypond:
        result = render_lilypond(Path(args.lilypond), Path(args.output_dir))
    else:
        parser.error("provide --musicxml or --lilypond")
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

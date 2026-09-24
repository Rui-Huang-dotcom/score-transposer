#!/usr/bin/env python3
"""Extract representative source-PDF pages for human comparison."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def page_count(pdf: Path) -> int | None:
    try:
        result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def prepare(pdf: str, output_dir: str) -> dict:
    source = Path(pdf)
    destination = Path(output_dir)
    count = page_count(source)
    if not shutil.which("pdftoppm") or count is None:
        return {"passed": False, "error": "pdftoppm or readable PDF is unavailable", "pages": count, "images": []}
    selected = sorted({1, count, max(1, (count + 1) // 2)})
    destination.mkdir(parents=True, exist_ok=True)
    images = []
    for page in selected:
        prefix = destination / f"source-page-{page}"
        result = subprocess.run(["pdftoppm", "-png", "-r", "150", "-f", str(page), "-l", str(page), "-singlefile", str(source), str(prefix)], capture_output=True, text=True, timeout=60)
        image = prefix.with_suffix(".png")
        if result.returncode == 0 and image.exists():
            images.append(str(image))
    return {"passed": len(images) == len(selected), "pages": count, "selected_pages": selected, "images": images, "requires_human_visual_review": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = prepare(args.input, args.output_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else result)
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

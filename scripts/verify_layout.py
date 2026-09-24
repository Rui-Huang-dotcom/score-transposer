#!/usr/bin/env python3
"""Check basic PDF output invariants; visual review remains necessary."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def pages(path: str) -> int | None:
    try:
        result = subprocess.run(["pdfinfo", path], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def verify(source_pdf: str, target_pdf: str) -> dict:
    source_pages = pages(source_pdf)
    target_pages = pages(target_pdf)
    issues = []
    if target_pages is None:
        issues.append("target PDF is unreadable or pdfinfo is unavailable")
    if source_pages is not None and target_pages is not None and target_pages != source_pages:
        issues.append(f"page count changed from {source_pages} to {target_pages}; inspect layout")
    return {"source_pdf": str(Path(source_pdf)), "target_pdf": str(Path(target_pdf)), "source_pages": source_pages, "target_pages": target_pages, "issues": issues, "passed": not issues}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pdf", required=True)
    parser.add_argument("--target-pdf", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify(args.source_pdf, args.target_pdf)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Layout verification: {'passed' if result['passed'] else 'manual review required'}")
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

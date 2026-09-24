#!/usr/bin/env python3
"""Compare score structure and rhythmic invariants before/after transposition."""

from __future__ import annotations

import argparse
import json
from collections import Counter

try:
    from .common import open_musicxml
except ImportError:
    from common import open_musicxml


def summary(path: str) -> dict:
    tree, _ = open_musicxml(path)
    root = tree.getroot()
    notes = root.findall(".//note")
    non_chord_notes = [n for n in notes if n.find("chord") is None]
    durations = Counter()
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            key = f"{part.get('id', '?')}:{measure.get('number', '?')}"
            durations[key] = sum(float(n.findtext("duration", "0")) for n in measure.findall("note") if n.find("chord") is None)
    return {
        "parts": len(root.findall("part")),
        "measures": len(root.findall(".//part/measure")),
        "noteheads": len(non_chord_notes),
        "chord_tones": len(root.findall(".//note/chord")),
        "rests": len(root.findall(".//note/rest")),
        "voices": sorted({v.text for v in root.findall(".//note/voice") if v.text}),
        "staves": sorted({s.text for s in root.findall(".//note/staff") if s.text}),
        "clefs": len(root.findall(".//clef")),
        "keys": len(root.findall(".//key")),
        "time_signatures": len(root.findall(".//time")),
        "lyrics": len(root.findall(".//lyric")),
        "ties": len(root.findall(".//tie")),
        "measure_durations": durations,
    }


def verify(source: str, target: str) -> dict:
    before = summary(source)
    after = summary(target)
    duration_mismatches = []
    for key in sorted(set(before["measure_durations"]) | set(after["measure_durations"])):
        if before["measure_durations"].get(key) != after["measure_durations"].get(key):
            duration_mismatches.append({"measure": key, "source": before["measure_durations"].get(key), "target": after["measure_durations"].get(key)})
    comparable = ["parts", "measures", "noteheads", "chord_tones", "rests", "voices", "staves", "clefs", "keys", "time_signatures", "lyrics", "ties"]
    mismatches = [{"field": field, "source": before[field], "target": after[field]} for field in comparable if before[field] != after[field]]
    mismatches.extend({"field": "measure_duration", **item} for item in duration_mismatches)
    return {"source": before, "target": after, "mismatches": mismatches, "passed": not mismatches}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.source, args.target)
    except (OSError, ValueError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False) if args.json else f"ERROR: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Structure verification: {'passed' if result['passed'] else 'failed'}")
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

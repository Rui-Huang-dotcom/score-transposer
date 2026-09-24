#!/usr/bin/env python3
"""Re-read source and final MusicXML and verify the requested pitch interval."""

from __future__ import annotations

import argparse
import json

try:
    from .common import iter_notes, key_interval, open_musicxml, pitch_midi, parse_key
except ImportError:
    from common import iter_notes, key_interval, open_musicxml, pitch_midi, parse_key


def verify(source: str, target: str, source_key: str, target_key: str) -> dict:
    source_tree, _ = open_musicxml(source)
    target_tree, _ = open_musicxml(target)
    source_notes = list(iter_notes(source_tree.getroot()))
    target_notes = list(iter_notes(target_tree.getroot()))
    expected, _ = key_interval(parse_key(source_key), parse_key(target_key))
    checked = min(len(source_notes), len(target_notes))
    mismatches = []
    for i in range(checked):
        src = source_notes[i]
        dst = target_notes[i]
        actual = pitch_midi(dst[3].find("pitch")) - pitch_midi(src[3].find("pitch"))
        if abs(actual - expected) > 1e-6:
            mismatches.append({"part": dst[0], "measure": dst[1], "note": dst[2], "expected_semitones": expected, "actual_semitones": actual})
    if len(source_notes) != len(target_notes):
        mismatches.append({"reason": "pitch-bearing note count differs", "source": len(source_notes), "target": len(target_notes)})
    return {"source_key": source_key, "target_key": target_key, "expected_semitones": expected, "verified": checked - len([m for m in mismatches if "actual_semitones" in m]), "total": checked, "mismatches": mismatches, "passed": not mismatches}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--target-key", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.source, args.target, args.source_key, args.target_key)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False) if args.json else f"ERROR: {exc}")
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Pitch verification: {result['verified']} / {result['total']} passed")
        for item in result["mismatches"][:10]:
            print(item)
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Semantically transpose MusicXML/MXL while preserving non-pitch notation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .common import LETTER_INDEX, STEP_TO_PC, iter_notes, key_interval, open_musicxml, parse_key, pitch_midi, safe_int, write_musicxml
except ImportError:
    from common import LETTER_INDEX, STEP_TO_PC, iter_notes, key_interval, open_musicxml, parse_key, pitch_midi, safe_int, write_musicxml


def transpose_note(pitch, semitones: int, diatonic_steps: int) -> tuple[bool, str | None]:
    step = pitch.findtext("step")
    octave_text = pitch.findtext("octave")
    alter_text = pitch.findtext("alter", "0")
    if step not in STEP_TO_PC or octave_text is None:
        return False, "missing or unknown pitch fields"
    try:
        octave = int(octave_text)
        old_alter = float(alter_text)
    except ValueError:
        return False, "non-numeric pitch field"
    if not old_alter.is_integer():
        return False, "fractional source alter is not safely supported"
    total_steps = LETTER_INDEX[step] + diatonic_steps
    new_letter_index = total_steps % 7
    new_octave = octave + total_steps // 7
    new_step = "CDEFGAB"[new_letter_index]
    absolute = pitch_midi(pitch) + semitones
    natural = 12 * (new_octave + 1) + STEP_TO_PC[new_step]
    new_alter = int(round(absolute - natural))
    if abs(absolute - (natural + new_alter)) > 1e-6 or abs(new_alter) > 2:
        return False, f"resulting alter {new_alter} is outside ordinary notation"
    pitch.find("step").text = new_step
    pitch.find("octave").text = str(new_octave)
    alter = pitch.find("alter")
    if new_alter:
        if alter is None:
            alter = __import__("xml.etree.ElementTree", fromlist=["Element"]).Element("alter")
            pitch.insert(1, alter)
        alter.text = str(new_alter)
    elif alter is not None:
        pitch.remove(alter)
    return True, None


def transpose_file(source: str, target: str, source_key_text: str, target_key_text: str) -> dict:
    source_key = parse_key(source_key_text)
    target_key = parse_key(target_key_text)
    semitones, diatonic_steps = key_interval(source_key, target_key)
    tree, _ = open_musicxml(source)
    root = tree.getroot()
    if root.find(".//transpose") is not None:
        raise ValueError("Score contains a transposing instrument; confirm written-pitch or concert-pitch mode first")
    issues = []
    notes_total = 0
    notes_changed = 0
    for part_id, measure_no, index, note in iter_notes(root):
        notes_total += 1
        ok, issue = transpose_note(note.find("pitch"), semitones, diatonic_steps)
        if ok:
            notes_changed += 1
        else:
            issues.append({"part": part_id, "measure": measure_no, "note": index, "reason": issue})

    first_source_fifths = None
    first_source_mode = None
    for key in root.findall(".//attributes/key"):
        fifths_element = key.find("fifths")
        mode_element = key.find("mode")
        if fifths_element is None:
            continue
        fifths = safe_int(fifths_element.text)
        mode = mode_element.text if mode_element is not None and mode_element.text in {"major", "minor"} else source_key.mode
        if first_source_fifths is None:
            first_source_fifths = fifths
            first_source_mode = mode
            if fifths != source_key.fifths:
                issues.append({"reason": "provided source key does not match the first MusicXML key signature", "provided": source_key.fifths, "found": fifths})
            if mode != source_key.mode:
                issues.append({"reason": "provided source mode does not match the first MusicXML key signature", "provided": source_key.mode, "found": mode})
        new_fifths = fifths + target_key.fifths - (first_source_fifths if first_source_fifths is not None else source_key.fifths)
        if new_fifths < -7 or new_fifths > 7:
            issues.append({"reason": f"key signature {new_fifths} exceeds standard MusicXML range"})
        else:
            fifths_element.text = str(new_fifths)
        if mode != source_key.mode or target_key.mode != source_key.mode:
            issues.append({"reason": "key mode change requires manual verification", "mode": mode})
    write_musicxml(tree, target)
    return {"source": str(source), "target": str(target), "source_key": source_key_text, "target_key": target_key_text, "semitones": semitones, "diatonic_steps": diatonic_steps, "notes_total": notes_total, "notes_changed": notes_changed, "issues": issues, "passed": not issues and notes_total == notes_changed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--target-key", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = transpose_file(args.source, args.target, args.source_key, args.target_key)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, ensure_ascii=False) if args.json else f"ERROR: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Transposed {result['notes_changed']}/{result['notes_total']} notes; issues={len(result['issues'])}")
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

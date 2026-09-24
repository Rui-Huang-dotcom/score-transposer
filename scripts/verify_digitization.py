#!/usr/bin/env python3
"""Quality gate for OMR-derived MusicXML and recognized-content completeness."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

try:
    from .common import open_musicxml
except ImportError:
    from common import open_musicxml


DIAGNOSTICS = [
    "no correct rhythm",
    "time inconsistency",
    "measure duration mismatch",
    "voice conflict",
    "nullpointerexception",
    r"export(?:ing)?\s+(?:failed|failure|exception)",
    r"missing\s+measure",
    "no ocr is available",
    "tesseract data could not be found",
    "could not initialize tessbaseapi",
    "ocr link error",
]
CONTENT_FIELDS = (
    "measures", "note_elements", "notes", "rests", "lyrics", "lyric_syllables",
    "dynamics", "slurs", "ties", "tuplets", "time_modifications", "articulations", "key_signatures",
    "time_signatures", "clefs", "tempo", "text", "octave_shifts", "fermatas", "ornaments",
)


def read_diagnostics(log_path: str | None) -> list[dict]:
    if not log_path:
        return []
    path = Path(log_path)
    if not path.exists():
        return [{"line": 0, "text": f"OMR log not found: {path}", "pattern": "missing_log"}]
    matches = []
    for line_number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        for pattern in DIAGNOSTICS:
            if re.search(pattern, line, re.I):
                page = re.search(r"\[.*?#(\d+)\]", line)
                stack = re.search(r"(?:MeasureStack|Measure)#(\d+)", line)
                matches.append({"line": line_number, "text": line[:500], "pattern": pattern, "location": {"page": int(page.group(1)) if page else None, "system_or_stack": int(stack.group(1)) if stack else None}})
                break
    return matches


def _score_type(root, requested: str) -> str:
    if requested in {"vocal", "instrumental"}:
        return requested
    if root.findall(".//lyric"):
        return "vocal"
    return "instrumental"


def _content_summary(root) -> dict:
    measures = root.findall(".//part/measure")
    note_elements = root.findall(".//note")
    notes = [note for note in note_elements if note.find("pitch") is not None or note.find("unpitched") is not None]
    rests = [note for note in note_elements if note.find("rest") is not None]
    lyrics = root.findall(".//lyric")
    return {
        "measures": len(measures),
        "note_elements": len(note_elements),
        "notes": len(notes),
        "rests": len(rests),
        "lyrics": len(lyrics),
        "lyric_syllables": sum(1 for lyric in lyrics if lyric.find("text") is not None and (lyric.findtext("text") or "").strip()),
        "dynamics": len(root.findall(".//dynamics/*")),
        "slurs": len(root.findall(".//slur")),
        "ties": len(root.findall(".//tie")),
        "tuplets": len(root.findall(".//tuplet")),
        "time_modifications": len(root.findall(".//time-modification")),
        "articulations": len(root.findall(".//articulations/*")),
        "key_signatures": len(root.findall(".//key")),
        "time_signatures": len(root.findall(".//time")),
        "clefs": len(root.findall(".//clef")),
        "tempo": len(root.findall(".//metronome")) + len(root.findall(".//sound[@tempo]")),
        "text": len(root.findall(".//words")) + len(root.findall(".//rehearsal")) + len(root.findall(".//expression")),
        "octave_shifts": len(root.findall(".//octave-shift")),
        "fermatas": len(root.findall(".//fermata")),
        "ornaments": len(root.findall(".//ornaments/*")),
    }


def _rhythm_issues(root) -> list[dict]:
    rhythm_issues = []
    for part in root.findall("part"):
        current_divisions = 1
        current_beats = None
        current_beat_type = None
        for measure_index, measure in enumerate(part.findall("measure"), 1):
            attributes = measure.find("attributes")
            if attributes is not None:
                try:
                    current_divisions = max(1, int(float(attributes.findtext("divisions", str(current_divisions)))))
                except ValueError:
                    rhythm_issues.append({"part": part.get("id", "?"), "measure": measure.get("number", "?"), "measure_index": measure_index, "reason": "invalid divisions"})
                    continue
                time = attributes.find("time")
                if time is not None:
                    current_beats = float(time.findtext("beats", "0"))
                    current_beat_type = float(time.findtext("beat-type", "4"))
            if current_beats is None or current_beat_type in {None, 0}:
                continue
            expected = current_beats * current_divisions * 4 / current_beat_type
            voices = {}
            for note in measure.findall("note"):
                if note.find("chord") is not None:
                    continue
                voice = note.findtext("voice", "1")
                try:
                    voices[voice] = voices.get(voice, 0.0) + float(note.findtext("duration", "0"))
                except ValueError:
                    pass
            if len(voices) == 1 and voices and abs(next(iter(voices.values())) - expected) > 1e-6:
                rhythm_issues.append({"part": part.get("id", "?"), "measure": measure.get("number", "?"), "measure_index": measure_index, "expected": expected, "found": next(iter(voices.values()))})
    return rhythm_issues


def inspect_musicxml(path: str, score_type: str = "auto", ocr_language: str | None = None) -> dict:
    tree, _ = open_musicxml(path)
    root = tree.getroot()
    issues = []
    content = _content_summary(root)
    resolved_score_type = _score_type(root, score_type)
    notes = root.findall(".//note")
    if not root.findall("part") or not root.findall(".//part/measure"):
        issues.append({"severity": "critical", "reason": "missing parts or measures"})
    for index, note in enumerate(notes, 1):
        if note.find("pitch") is None and note.find("rest") is None and note.find("unpitched") is None:
            issues.append({"severity": "critical", "note": index, "reason": "note has neither pitch, rest, nor unpitched content"})
        if note.find("grace") is None:
            try:
                duration = float(note.findtext("duration", "0"))
            except ValueError:
                duration = 0
            if duration <= 0:
                issues.append({"severity": "critical", "note": index, "reason": "missing or non-positive duration"})
        pitch = note.find("pitch")
        if pitch is not None:
            if pitch.findtext("step") not in {"A", "B", "C", "D", "E", "F", "G"}:
                issues.append({"severity": "critical", "note": index, "reason": "unknown pitch step"})
            try:
                int(pitch.findtext("octave", ""))
            except ValueError:
                issues.append({"severity": "critical", "note": index, "reason": "missing or invalid pitch octave"})
    allowed_clefs = {"G", "F", "C", "percussion", "TAB", "none"}
    for clef in root.findall(".//clef"):
        sign = clef.findtext("sign")
        if sign not in allowed_clefs:
            issues.append({"severity": "critical", "reason": f"unknown clef sign: {sign}"})
    for alter in root.findall(".//pitch/alter"):
        try:
            float(alter.text or "0")
        except ValueError:
            issues.append({"severity": "critical", "reason": "non-numeric pitch alter"})
    rhythm_issues = _rhythm_issues(root)
    issues.extend({"severity": "critical", "reason": "measure duration mismatch", **item} for item in rhythm_issues)
    empty_measures = []
    for part in root.findall("part"):
        for measure in part.findall("measure"):
            if not measure.findall("note"):
                empty_measures.append({"part": part.get("id", "?"), "measure": measure.get("number", "?")})
    warnings = []
    if resolved_score_type == "vocal" and content["lyrics"] == 0:
        warnings.append("Vocal score detected but no lyrics were exported")
        issues.append({"severity": "critical", "reason": "missing lyrics in vocal score"})
    if empty_measures:
        warnings.append(f"{len(empty_measures)} empty measures")
    return {
        **content,
        "score_type": resolved_score_type,
        "ocr_language": ocr_language,
        "duration_errors": len(rhythm_issues),
        "rhythm_issues": rhythm_issues,
        "empty_measures": empty_measures,
        "suspicious_measures": rhythm_issues + empty_measures,
        "issues": issues,
        "warnings": warnings,
    }


def verify_content_preservation(source: str, target: str, score_type: str = "auto") -> dict:
    source_tree, _ = open_musicxml(source)
    target_tree, _ = open_musicxml(target)
    source_summary = _content_summary(source_tree.getroot())
    target_summary = _content_summary(target_tree.getroot())
    differences = {field: {"source": source_summary[field], "target": target_summary[field]} for field in CONTENT_FIELDS if source_summary[field] != target_summary[field]}
    warnings = []
    if score_type == "vocal" and target_summary["lyrics"] == 0:
        warnings.append("Vocal score has no lyrics after transposition")
    return {"source": source_summary, "target": target_summary, "differences": differences, "warnings": warnings, "passed": not differences and not warnings}


def verify(musicxml: str, omr_log: str | None = None, source_pdf: str | None = None, score_type: str = "auto", ocr_language: str | None = None) -> dict:
    diagnostics = read_diagnostics(omr_log)
    inspection = inspect_musicxml(musicxml, score_type, ocr_language)
    review_candidates = []
    if source_pdf:
        review_candidates.extend(["first page", "last page"])
    tree, _ = open_musicxml(musicxml)
    root = tree.getroot()
    for label, xpath in (("accidental", ".//accidental"), ("clef change", ".//attributes/clef"), ("dense chord", ".//note/chord"), ("ornament", ".//ornaments"), ("complex rhythm", ".//time-modification")):
        if root.findall(xpath):
            review_candidates.append(label)
    pitches = []
    for pitch in root.findall(".//pitch"):
        try:
            pitches.append(int(pitch.findtext("octave", "0")))
        except ValueError:
            pass
    if pitches:
        review_candidates.extend(["lowest register", "highest register"])
    critical = bool(diagnostics or inspection["issues"])
    return {"musicxml": str(musicxml), "source_pdf": source_pdf, "score_type": inspection["score_type"], "ocr_language": ocr_language, "omr_diagnostics": diagnostics, "inspection": inspection, "auto_repairs": [], "review_candidates": review_candidates, "repair_required": critical, "formal_delivery": not critical, "passed": not critical}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--musicxml", required=True)
    parser.add_argument("--source-pdf")
    parser.add_argument("--omr-log")
    parser.add_argument("--score-type", choices=["auto", "vocal", "instrumental"], default="auto")
    parser.add_argument("--ocr-language", default="auto")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify(args.musicxml, args.omr_log, args.source_pdf, args.score_type, args.ocr_language)
    except (OSError, ValueError) as exc:
        result = {"passed": False, "formal_delivery": False, "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else f"Digitization QA: {'passed' if result['passed'] else 'manual review required'}")
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())

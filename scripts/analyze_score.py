#!/usr/bin/env python3
"""Analyze PDF or MusicXML structure and choose a conservative route."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

try:
    from .common import open_musicxml, score_has_transposition
except ImportError:
    from common import open_musicxml, score_has_transposition


def pdf_pages(path: Path) -> int | None:
    try:
        result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=10)
        for line in result.stdout.splitlines():
            if line.startswith("Pages:"):
                return int(line.split(":", 1)[1].strip())
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return None


def pdf_structure(path: Path) -> dict:
    """Classify PDF evidence without pretending PDF graphics are MusicXML."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        return {"pdf_type": "scan", "confidence": "low", "reason": f"PDF bytes unavailable: {exc}", "semantic_structure_available": False}
    fonts = len(re.findall(rb"/(?:Type\s*)?Font\b", data))
    embedded_fonts = len(re.findall(rb"/FontFile(?:2|3)?\b", data))
    text_operators = len(re.findall(rb"\b(?:BT|ET|Tf|Tj|TJ)\b", data))
    drawing_operators = len(re.findall(rb"\b(?:m|l|c|re|S|f)\b", data))
    image_objects = list(re.finditer(rb"/Subtype\s*/Image\b", data))
    large_images = 0
    for image in image_objects:
        window = data[image.start():image.start() + 1200]
        width = re.search(rb"/Width\s+(\d+)", window)
        height = re.search(rb"/Height\s+(\d+)", window)
        if width and height and int(width.group(1)) * int(height.group(1)) >= 1_000_000:
            large_images += 1
    pages = pdf_pages(path)
    # Raw PDF scanning cannot reliably distinguish path operators from bytes
    # inside compressed image streams, so drawing tokens are reported but are
    # not sufficient on their own to call a PDF vector-based.
    vector_evidence = fonts > 0 or embedded_fonts > 0 or text_operators >= 8
    full_page_images = large_images >= max(pages or 1, 1)
    if full_page_images and not vector_evidence:
        pdf_type, confidence, reason = "scan", "high", "each page is represented by a large raster image without vector/text evidence"
    elif vector_evidence and not full_page_images:
        pdf_type, confidence, reason = "vector", "medium", "fonts, text, or drawing operators are present without page-sized raster images"
    else:
        pdf_type, confidence, reason = "scan", "low", "mixed or insufficient PDF evidence; using the conservative scan route"
    return {
        "pdf_type": pdf_type,
        "confidence": confidence,
        "reason": reason,
        "pages": pages,
        "embedded_font_objects": embedded_fonts,
        "font_objects": fonts,
        "text_operator_count": text_operators,
        "drawing_operator_count": drawing_operators,
        "image_objects": len(image_objects),
        "large_image_objects": large_images,
        "page_sized_raster_evidence": full_page_images,
        "semantic_structure_available": False,
        "semantic_structure_note": "PDF drawing/text objects are retained as analysis evidence, but are not treated as reliable MusicXML semantics.",
    }


def analyze(path: str) -> dict:
    file = Path(path)
    if file.suffix.lower() == ".pdf":
        structure = pdf_structure(file)
        pages = structure.get("pages")
        complexity = "complex" if pages is None or pages > 8 else "medium" if pages > 4 else "simple"
        route = "pdf_structure_analysis_then_omr_if_needed" if structure["pdf_type"] == "vector" else "audiveris_then_homr_fallback_then_qa"
        flags = ["semantic_omr_required", f"pdf_{structure['pdf_type']}"]
        if structure["pdf_type"] == "vector":
            flags.append("vector_structure_analysis_first")
        verification_reasons = []
        if structure["pdf_type"] == "scan":
            verification_reasons.append("scanned_or_image_pdf")
        if pages and pages > 1:
            verification_reasons.append("multi_page_score")
        if complexity != "simple":
            verification_reasons.append(f"{complexity}_score")
        return {
            "input": str(file),
            "kind": "pdf",
            "pages": pages,
            "pdf_type": structure["pdf_type"],
            "pdf_structure": structure,
            "complexity": complexity,
            "route": route,
            "risk": "high" if complexity == "complex" else "medium" if complexity == "medium" else "low",
            "flags": flags,
            "recommended_mode": "verified" if verification_reasons else "fast",
            "verification_reasons": verification_reasons,
        }
    tree, _ = open_musicxml(file)
    root = tree.getroot()
    parts = root.findall("part")
    measures = root.findall(".//part/measure")
    notes = root.findall(".//note[pitch]")
    rests = root.findall(".//note[rest]")
    chords = root.findall(".//note[chord]")
    clefs = root.findall(".//clef")
    keys = root.findall(".//key")
    time_signatures = root.findall(".//time")
    voices = {e.text for e in root.findall(".//note/voice") if e.text}
    lyrics = root.findall(".//lyric")
    dynamics = root.findall(".//dynamics/*")
    slurs = root.findall(".//slur")
    ties = root.findall(".//tie")
    articulations = root.findall(".//articulations/*")
    fermatas = root.findall(".//fermata")
    ornaments = root.findall(".//ornaments/*")
    flags = []
    if len(parts) > 1:
        flags.append("multiple_parts")
    if len(parts) > 1 or len(root.findall(".//attributes/staves")) or len(clefs) > len(parts):
        flags.append("multiple_staves_or_clef_changes")
    if len(voices) > 1:
        flags.append("multiple_voices")
    if chords:
        flags.append("dense_chords" if len(chords) > 24 else "chords")
    if root.findall(".//grace"):
        flags.append("grace_notes")
    if root.findall(".//time-modification"):
        flags.append("tuplets")
    if ornaments:
        flags.append("ornaments")
    if root.findall(".//backup") or root.findall(".//forward"):
        flags.append("polyphonic_timeline")
    if score_has_transposition(root):
        flags.append("possible_transposing_instrument")
    fractional = False
    for element in root.findall(".//pitch/alter"):
        try:
            fractional |= float(element.text or "0") != int(float(element.text or "0"))
        except ValueError:
            fractional = True
    if fractional:
        flags.append("fractional_alter")
    risk = "high" if {"possible_transposing_instrument", "fractional_alter"} & set(flags) else "medium" if len(flags) >= 2 or len(parts) > 1 else "low"
    complexity = "complex" if risk == "high" or len(flags) >= 4 or len(measures) > 128 else "medium" if flags else "simple"
    route = "lilypond" if complexity == "simple" and len(measures) <= 32 and len(parts) <= 2 else "audiveris_then_musescore"
    verification_reasons = []
    if lyrics:
        verification_reasons.append("lyrics_present")
    if complexity != "simple":
        verification_reasons.append(f"{complexity}_score")
    if any((slurs, ties, articulations, dynamics, fermatas, ornaments)):
        verification_reasons.append("notation_preservation_required")
    return {
        "input": str(file),
        "kind": "musicxml",
        "parts": len(parts),
        "measures": len(measures),
        "noteheads": len(notes) - len(chords),
        "chord_tones": len(chords),
        "rests": len(rests),
        "voices": len(voices),
        "clefs": len(clefs),
        "keys": len(keys),
        "time_signatures": len(time_signatures),
        "lyrics": len(lyrics),
        "dynamics": len(dynamics),
        "slurs": len(slurs),
        "ties": len(ties),
        "articulations": len(articulations),
        "fermatas": len(fermatas),
        "ornaments": len(ornaments),
        "score_type": "vocal" if lyrics else "instrumental",
        "complexity": complexity,
        "route": route,
        "risk": risk,
        "flags": flags,
        "recommended_mode": "fast",
        "verification_reasons": verification_reasons,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = analyze(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else "\n".join(f"{key}: {value}" for key, value in result.items()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

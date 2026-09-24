#!/usr/bin/env python3
"""Visual review, progress tracking, and safe MusicXML patching for detailed mode."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

try:
    from .common import open_musicxml, write_musicxml
except ImportError:
    from common import open_musicxml, write_musicxml


MAX_ACTIVE_REGIONS = 8
REVIEW_DONE_STATUSES = {"verified", "passed", "cached"}
REPAIR_PRIORITY = {
    "lyrics": 10,
    "lyrics_missing": 10,
    "duration_error": 20,
    "rhythm_error": 20,
    "tuplet_anomaly": 30,
    "clef_anomaly": 40,
    "octave_anomaly": 50,
    "accidental_anomaly": 60,
    "slur_anomaly": 70,
    "tie_anomaly": 70,
    "dynamics_anomaly": 80,
    "articulation_anomaly": 80,
    "omr_log_error": 90,
}


def review_item_status(item: dict | None) -> str:
    item = item or {}
    if item.get("page_verified") is True or item.get("verified_status") in {True, "verified", "passed", "cached"}:
        return "verified"
    if item.get("repair_status") in {"repaired", "applied"}:
        return "repaired"
    return str(item.get("status", "pending"))


def _pdf_pages(path: str | None) -> int | None:
    if not path:
        return None
    try:
        result = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"^Pages:\s*(\d+)", result.stdout, re.MULTILINE)
    return int(match.group(1)) if match else None


def _cached_ids(cache: dict | None) -> set[str]:
    return {
        region.get("id")
        for region in (cache or {}).get("regions", [])
        if region.get("id") and review_item_status(region) in REVIEW_DONE_STATUSES
    }


def _cached_page_ids(cache: dict | None, field: str = "page_checks") -> set[str]:
    review = (cache or {}).get("verified_review", cache or {})
    return {
        page.get("id")
        for page in review.get(field, [])
        if page.get("id") and review_item_status(page) in REVIEW_DONE_STATUSES
    }


def _add(regions: list[dict], seen: set[str], *, reason: str, measure: str | None = None, part: str | None = None, page: int | None = None, system: int | None = None, detail: str | None = None) -> None:
    if page is not None or system is not None:
        identity = f"page:{page or '?'}:system:{system or '?'}"
    elif part is not None or measure is not None:
        identity = f"part:{part or '?'}:measure:{measure or '?'}"
    else:
        identity = f"global:{reason}"
    if identity in seen:
        existing = next(region for region in regions if region["id"] == identity)
        existing.setdefault("reasons", [existing["reason"]])
        if reason not in existing["reasons"]:
            existing["reasons"].append(reason)
        if detail:
            existing["detail"] = f"{existing.get('detail') or ''}\n{detail}".strip()
        existing["priority"] = min(existing.get("priority", 90), REPAIR_PRIORITY.get(reason, 90))
        return
    seen.add(identity)
    regions.append({
        "id": identity,
        "reason": reason,
        "reasons": [reason],
        "priority": REPAIR_PRIORITY.get(reason, 90),
        "part": part,
        "measure": measure,
        "source_page": page,
        "source_system": system,
        "detail": detail,
        "status": "pending",
        "repair_status": "pending",
        "verified_status": False,
        "visual_check": "required",
    })


def prepare_visual_comparison(
    source_pdf: str | None,
    rendered_pdf: str | None,
    output_dir: str | None,
    cache: dict | None = None,
    cache_field: str = "page_checks",
    page_numbers: list[int] | None = None,
) -> dict:
    """Prepare source/rendered page pairs for the requested pages.

    This only extracts comparison images. A verified review file records whether
    the pair was visually checked, so the caller can inspect it once without
    reopening already accepted pages.
    """
    source_pages = _pdf_pages(source_pdf)
    rendered_pages = _pdf_pages(rendered_pdf)
    result = {
        "source_pdf": source_pdf,
        "rendered_pdf": rendered_pdf,
        "source_pages": source_pages,
        "rendered_pages": rendered_pages,
        "pages": [],
        "status": "not_prepared",
    }
    if not source_pdf or not rendered_pdf or not source_pages or not rendered_pages:
        return result
    available = min(source_pages, rendered_pages)
    selected = sorted({page for page in (page_numbers or range(1, available + 1)) if 1 <= page <= available})
    cached_pages = _cached_page_ids(cache, cache_field)
    destination = Path(output_dir) if output_dir else None
    if destination:
        destination.mkdir(parents=True, exist_ok=True)
    for page_number in selected:
        page_id = f"page:{page_number}"
        source_image = destination / f"page-{page_number:03d}-source.png" if destination else None
        rendered_image = destination / f"page-{page_number:03d}-rendered.png" if destination else None
        if destination and page_id not in cached_pages:
            for pdf, image in ((source_pdf, source_image), (rendered_pdf, rendered_image)):
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "150", "-f", str(page_number), "-l", str(page_number), "-singlefile", str(pdf), str(image.with_suffix(""))],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
        result["pages"].append({
            "id": page_id,
            "page": page_number,
            "source_image": str(source_image) if source_image else None,
            "rendered_image": str(rendered_image) if rendered_image else None,
            "status": "cached" if page_id in cached_pages else "pending",
            "page_verified": page_id in cached_pages,
            "visual_check": "skipped_cached" if page_id in cached_pages else "required",
        })
    result["status"] = "page_pairs_prepared" if source_pages == rendered_pages else "page_count_mismatch"
    result["selected_pages"] = selected
    return result


def merge_page_checks(previous: list[dict] | None, current: list[dict] | None) -> list[dict]:
    merged = {page.get("id"): dict(page) for page in (previous or []) if page.get("id")}
    for page in current or []:
        if page.get("id"):
            merged[page["id"]] = dict(page)
    return [merged[key] for key in sorted(merged, key=lambda value: int(value.split(":", 1)[1]))]


def build_review_plan(
    qa: dict,
    source_pdf: str | None = None,
    cache: dict | None = None,
    max_regions: int = MAX_ACTIVE_REGIONS,
    visual_comparison: dict | None = None,
    repair_round: int = 0,
) -> dict:
    inspection = qa.get("inspection", qa)
    diagnostics = qa.get("omr_diagnostics", [])
    regions: list[dict] = []
    seen: set[str] = set()
    cached = _cached_ids(cache)
    previous_review = (cache or {}).get("verified_review", cache or {})

    if inspection.get("duration_errors", 0):
        for issue in inspection.get("rhythm_issues", []):
            _add(regions, seen, reason="duration_error", part=issue.get("part"), measure=str(issue.get("measure", "?")), detail=str(issue))
    if inspection.get("score_type") == "vocal" and inspection.get("lyrics", 0) == 0:
        _add(regions, seen, reason="lyrics_missing", detail="vocal score has no exported lyrics")
    for issue in inspection.get("empty_measures", []):
        _add(regions, seen, reason="empty_measure", part=issue.get("part"), measure=str(issue.get("measure", "?")))
    for issue in inspection.get("suspicious_measures", []):
        _add(regions, seen, reason="suspicious_measure", part=issue.get("part"), measure=str(issue.get("measure", "?")), detail=str(issue))

    for diagnostic in diagnostics:
        text = diagnostic.get("text", "")
        lowered = text.lower()
        if "duration" in lowered or "rhythm" in lowered or "tuplet" in lowered:
            reason = "rhythm_error" if "tuplet" not in lowered else "tuplet_anomaly"
        elif "clef" in lowered:
            reason = "clef_anomaly"
        elif "8va" in lowered or "8vb" in lowered or "octave" in lowered:
            reason = "octave_anomaly"
        elif "accidental" in lowered or "alter" in lowered:
            reason = "accidental_anomaly"
        elif "slur" in lowered:
            reason = "slur_anomaly"
        elif "tie" in lowered:
            reason = "tie_anomaly"
        elif "dynamic" in lowered:
            reason = "dynamics_anomaly"
        elif "articulation" in lowered or "ornament" in lowered:
            reason = "articulation_anomaly"
        else:
            reason = "omr_log_error"
        location = diagnostic.get("location", {})
        _add(regions, seen, reason=reason, page=location.get("page"), system=location.get("system_or_stack"), detail=text[:500])

    regions.sort(key=lambda region: (region.get("priority", 90), region["id"]))
    pending = [region for region in regions if region["id"] not in cached]
    selected = pending[:max_regions]
    for region in regions:
        if region["id"] in cached:
            region["status"] = "cached"
            region["repair_status"] = "cached"
            region["verified_status"] = True
            region["visual_check"] = "skipped_cached"
    comparison = visual_comparison or {"status": "not_prepared", "pages": []}
    page_checks = comparison.get("pages", [])
    pending_pages = [page for page in page_checks if review_item_status(page) not in REVIEW_DONE_STATUSES]
    visual_ready = bool(page_checks) and not pending_pages and comparison.get("status") == "page_pairs_prepared"
    return {
        "mode": "verified",
        "source_pdf": source_pdf,
        "max_active_regions": max_regions,
        "repair_round": repair_round,
        "candidate_count": len(pending),
        "regions": selected,
        "page_checks": page_checks,
        "visual_comparison": comparison,
        "cached_region_ids": sorted(cached),
        "skipped_region_count": max(0, len(pending) - len(selected)),
        "pending_page_count": len(pending_pages),
        "unresolved_region_count": len(pending),
        "stagnant_rounds": int(previous_review.get("stagnant_rounds", 0)),
        "depth_repair_blocked": bool(previous_review.get("depth_repair_blocked", False)),
        "formal_delivery": not pending and not (len(pending) - len(selected)) and visual_ready,
        "warning": None,
    }


def refresh_review_gate(plan: dict, stagnant: bool = False) -> dict:
    """Recompute the delivery gate after one repair/review round."""
    pending_pages = [page for page in plan.get("page_checks", []) if review_item_status(page) not in REVIEW_DONE_STATUSES]
    pending_selected = [region for region in plan.get("regions", []) if review_item_status(region) not in REVIEW_DONE_STATUSES]
    unresolved = len(pending_selected) + int(plan.get("skipped_region_count", 0))
    plan["pending_page_count"] = len(pending_pages)
    plan["unresolved_region_count"] = unresolved
    if stagnant:
        plan["stagnant_rounds"] = int(plan.get("stagnant_rounds", 0)) + 1
        plan["depth_repair_blocked"] = True
        plan["warning"] = "A repair round produced no material improvement; remaining differences require manual confirmation."
    plan["formal_delivery"] = bool(
        not plan.get("depth_repair_blocked")
        and not pending_pages
        and unresolved == 0
        and bool(plan.get("page_checks"))
        and plan.get("visual_comparison", {}).get("status") == "page_pairs_prepared"
    )
    return plan


def load_review(path: str | None) -> dict | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_review_patches(source: str, review: dict, target: str) -> dict:
    """Apply only explicit, local, structure-level corrections from a review file."""
    tree, _ = open_musicxml(source)
    root = tree.getroot()
    applied = []
    errors = []
    for region in review.get("regions", []):
        if review_item_status(region) not in {"verified", "repaired"}:
            continue
        for patch in region.get("patches", []):
            try:
                part = next(part for part in root.findall("part") if part.get("id") == patch["part"])
                measure = next(measure for measure in part.findall("measure") if str(measure.get("number")) == str(patch["measure"]))
                operation = patch["op"]
                note = None
                if "note_index" in patch:
                    notes = measure.findall("note")
                    note = notes[int(patch["note_index"]) - 1]
                elif operation in {"set-note-duration", "set-note-type", "set-lyric", "set-accidental", "set-tuplet", "set-slur", "set-tie", "set-articulation"}:
                    raise KeyError("note_index")
                if operation == "set-note-duration":
                    duration = note.find("duration")
                    if duration is None:
                        import xml.etree.ElementTree as ET
                        duration = ET.SubElement(note, "duration")
                    duration.text = str(patch["duration"])
                elif operation == "set-note-type":
                    note_type = note.find("type")
                    if note_type is None:
                        import xml.etree.ElementTree as ET
                        note_type = ET.SubElement(note, "type")
                    note_type.text = str(patch["value"])
                elif operation == "set-lyric":
                    verse = str(patch.get("verse", "1"))
                    lyric = next((item for item in note.findall("lyric") if str(item.get("number", "1")) == verse), None)
                    if lyric is None:
                        import xml.etree.ElementTree as ET
                        lyric = ET.SubElement(note, "lyric", {"number": verse})
                    text = lyric.find("text")
                    if text is None:
                        import xml.etree.ElementTree as ET
                        text = ET.SubElement(lyric, "text")
                    text.text = str(patch["text"])
                    syllabic = lyric.find("syllabic")
                    if syllabic is None:
                        import xml.etree.ElementTree as ET
                        syllabic = ET.SubElement(lyric, "syllabic")
                    syllabic.text = patch.get("syllabic", "single")
                elif operation == "set-accidental":
                    accidental = note.find("accidental")
                    if accidental is None:
                        import xml.etree.ElementTree as ET
                        accidental = ET.SubElement(note, "accidental")
                    accidental.text = str(patch["value"])
                elif operation == "set-tuplet":
                    import xml.etree.ElementTree as ET
                    time_modification = note.find("time-modification")
                    if time_modification is None:
                        time_modification = ET.SubElement(note, "time-modification")
                    for tag, key in (("actual-notes", "actual_notes"), ("actual-type", "actual_type"), ("normal-notes", "normal_notes"), ("normal-type", "normal_type")):
                        if key in patch:
                            child = time_modification.find(tag)
                            if child is None:
                                child = ET.SubElement(time_modification, tag)
                            child.text = str(patch[key])
                elif operation == "set-clef":
                    import xml.etree.ElementTree as ET
                    attributes = measure.find("attributes")
                    if attributes is None:
                        attributes = ET.SubElement(measure, "attributes")
                    clefs = attributes.findall("clef")
                    clef_index = max(0, int(patch.get("clef_index", 1)) - 1)
                    while len(clefs) <= clef_index:
                        clefs.append(ET.SubElement(attributes, "clef", {"number": str(len(clefs) + 1)}))
                    clef = clefs[clef_index]
                    for tag in ("sign", "line", "clef-octave-change"):
                        if tag in patch:
                            child = clef.find(tag)
                            if child is None:
                                child = ET.SubElement(clef, tag)
                            child.text = str(patch[tag])
                elif operation == "set-octave-shift":
                    import xml.etree.ElementTree as ET
                    action = patch.get("action", "add")
                    directions = measure.findall("direction")
                    matches = []
                    for direction in directions:
                        octave_shift = direction.find("direction-type/octave-shift")
                        if octave_shift is not None and str(octave_shift.get("number", "1")) == str(patch.get("number", "1")):
                            matches.append((direction, octave_shift))
                    if action == "remove":
                        for direction, _ in matches:
                            measure.remove(direction)
                    else:
                        direction = matches[0][0] if matches else ET.SubElement(measure, "direction")
                        direction_type = direction.find("direction-type")
                        if direction_type is None:
                            direction_type = ET.SubElement(direction, "direction-type")
                        octave_shift = direction_type.find("octave-shift")
                        if octave_shift is None:
                            octave_shift = ET.SubElement(direction_type, "octave-shift")
                        octave_shift.set("type", str(patch.get("type", "up")))
                        octave_shift.set("size", str(patch.get("size", 8)))
                        if patch.get("number") is not None:
                            octave_shift.set("number", str(patch["number"]))
                elif operation in {"set-slur", "set-tie", "set-articulation"}:
                    import xml.etree.ElementTree as ET
                    action = patch.get("action", "add")
                    number = str(patch.get("number", "1"))
                    if operation == "set-slur":
                        container = note.find("notations")
                        if container is None:
                            container = ET.SubElement(note, "notations")
                        tag = "slur"
                    elif operation == "set-tie":
                        tag = "tie"
                        container = note
                    else:
                        notations = note.find("notations")
                        if notations is None:
                            notations = ET.SubElement(note, "notations")
                        container = notations.find("articulations")
                        if container is None:
                            container = ET.SubElement(notations, "articulations")
                        tag = str(patch["value"])
                    existing = [child for child in container.findall(tag) if str(child.get("number", "1")) == number]
                    if action == "remove":
                        for child in existing:
                            container.remove(child)
                    elif not existing:
                        child = ET.SubElement(container, tag)
                        if operation != "set-articulation":
                            child.set("type", str(patch.get("type", "start")))
                            child.set("number", number)
                elif operation == "set-dynamics":
                    import xml.etree.ElementTree as ET
                    direction = ET.SubElement(measure, "direction", {"placement": str(patch.get("placement", "below"))})
                    direction_type = ET.SubElement(direction, "direction-type")
                    dynamics = ET.SubElement(direction_type, "dynamics")
                    ET.SubElement(dynamics, str(patch["value"]))
                else:
                    raise ValueError(f"unsupported review patch: {operation}")
                applied.append({"region": region.get("id"), "patch": patch})
            except (KeyError, IndexError, StopIteration, TypeError, ValueError, AttributeError) as exc:
                errors.append({"region": region.get("id"), "patch": patch, "error": str(exc)})
    write_musicxml(tree, target)
    return {"applied": applied, "errors": errors, "passed": not errors}

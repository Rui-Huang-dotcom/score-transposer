#!/usr/bin/env python3
"""PDF/MusicXML transpose pipeline with independent OMR and content gates."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from analyze_score import analyze
from common import open_musicxml, write_musicxml
from omr import retain_omr_logs, run_omr
from transpose_musicxml import transpose_file
from verify_digitization import verify as verify_digitization
from verify_digitization import verify_content_preservation
from verify_layout import verify as verify_layout
from verify_pitch import verify as verify_pitch
from verify_score_structure import verify as verify_structure
from verified_review import apply_review_patches, build_review_plan, load_review, merge_page_checks, prepare_visual_comparison, refresh_review_gate, review_item_status


def _render(musicxml: Path, pdf: Path) -> dict:
    rendered = subprocess.run([sys.executable, str(Path(__file__).with_name("render_output.py")), "--musicxml", str(musicxml), "--output-pdf", str(pdf), "--json"], capture_output=True, text=True)
    try:
        return json.loads(rendered.stdout)
    except json.JSONDecodeError:
        return {"passed": False, "error": "PDF rendering failed", "stderr": rendered.stderr[-2000:]}


def _write_report(report: dict, output_dir: Path, stem: str) -> Path:
    report_path = output_dir / f"{stem}_qa.json"
    report["qa_report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report_path


def _normalise_mode(mode: str) -> str:
    return "verified" if mode == "high-accuracy" else mode


def _review_status_is_done(status: str | None) -> bool:
    return status in {"verified", "passed", "cached"}


def _apply_review_statuses(plan: dict, review: dict, field: str = "page_checks") -> None:
    page_statuses = {item.get("id"): review_item_status(item) for item in review.get(field, [])}
    pages = plan.get(field, [])
    for page in pages:
        if page.get("id") in page_statuses and _review_status_is_done(page_statuses[page["id"]]):
            page["status"] = page_statuses[page["id"]]
            page["page_verified"] = True
            page["visual_check"] = "completed"
    if field == "page_checks":
        plan["pending_page_count"] = sum(not _review_status_is_done(page.get("status")) for page in pages)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--source-key", required=True)
    parser.add_argument("--target-key", required=True)
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--format", choices=["pdf", "musicxml", "pdf-musicxml", "pdf-musicxml-lilypond"], default="pdf-musicxml")
    parser.add_argument("--mode", choices=["auto", "fast", "accurate", "verified", "high-accuracy"], default="auto", help="verified/high-accuracy enables bounded anomaly review; default modes are unchanged")
    parser.add_argument("--score-type", choices=["auto", "vocal", "instrumental"], default="auto")
    parser.add_argument("--ocr-language", default="auto", help="Audiveris OCR language, for example eng, chi_sim, or chi_sim+eng")
    parser.add_argument("--review-json", help="verified mode: explicit visual-review results and local MusicXML patches")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze(str(source))
    requested_mode = _normalise_mode(args.mode)
    mode = requested_mode
    if requested_mode == "auto":
        mode = analysis.get("recommended_mode", "fast")
    report = {"task": "transpose", "input": str(source), "source_key": args.source_key, "target_key": args.target_key, "requested_mode": requested_mode, "mode": mode, "score_type": args.score_type, "ocr_language": args.ocr_language, "analysis": analysis, "outputs": [], "draft_outputs": [], "qa": {}, "risk": analysis.get("risk", "high"), "passed": False, "formal_delivery": False}
    if analysis.get("pdf_type") == "vector":
        report["qa"]["pdf_structure"] = analysis.get("pdf_structure", {})
        report["qa"]["pdf_structure"]["omr_fallback_reason"] = "Vector PDF structure was analyzed first; OMR is used only because PDF graphics are not reliable MusicXML semantics."
    workdir = Path(tempfile.mkdtemp(prefix="score-transposer-"))
    try:
        xml_source = source
        resolved_score_type = args.score_type
        if source.suffix.lower() == ".pdf":
            xml_source, omr = run_omr(source, workdir, args.score_type, args.ocr_language)
            report["qa"]["omr"] = retain_omr_logs(omr, output_dir, source.stem)
            resolved_score_type = omr.get("score_type", args.score_type)
            if xml_source is None:
                report["warning"] = "OMR did not produce a usable MusicXML file; transposition was not attempted."
                return_code = 3
                return _finish(report, output_dir, source.stem, args.json, return_code)
            log = omr.get("attempts", [{}])[-1].get("log") if omr.get("attempts") else None
            digitization = verify_digitization(str(xml_source), log, str(source), resolved_score_type, omr.get("ocr_language"))
            report["qa"]["digitization"] = digitization
            if requested_mode == "auto":
                auto_reasons = list(analysis.get("verification_reasons", []))
                if resolved_score_type == "vocal":
                    auto_reasons.append("vocal_score")
                if not digitization.get("passed") or digitization.get("review_candidates"):
                    auto_reasons.append("omr_or_content_qa_warning")
                if auto_reasons:
                    mode = "verified"
                    report["mode"] = mode
                    report["auto_verification_reasons"] = sorted(set(auto_reasons))
            if mode == "verified":
                previous = output_dir / f"{source.stem}_qa.json"
                cached = {}
                if previous.exists():
                    try:
                        cached = json.loads(previous.read_text(encoding="utf-8")).get("qa", {}).get("verified_review", {})
                    except (OSError, json.JSONDecodeError):
                        cached = {}
                pre_render_pdf = workdir / f"{source.stem}_omr_verified.pdf"
                pre_render = _render(xml_source, pre_render_pdf)
                report["qa"]["verified_render"] = pre_render
                visual = prepare_visual_comparison(
                    str(source),
                    str(pre_render_pdf) if pre_render.get("passed") else None,
                    str(output_dir / "_intermediate" / f"{source.stem}_verified_visual"),
                    cached,
                )
                plan = build_review_plan(digitization, str(source), cached, visual_comparison=visual)
                review_manifest = output_dir / f"{source.stem}_verified_review.json"
                review_manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                review_payload = None
                if args.review_json and not plan["depth_repair_blocked"]:
                    review_payload = load_review(args.review_json)
                    rounds = review_payload.get("rounds") or [review_payload]
                    current_xml = xml_source
                    for round_number, review in enumerate(rounds, 1):
                        allowed = {region["id"] for region in plan["regions"]}
                        review = dict(review)
                        review["regions"] = [region for region in review.get("regions", []) if region.get("id") in allowed]
                        reviewed = workdir / f"{source.stem}_verified_round{round_number}.musicxml"
                        patch_result = apply_review_patches(str(current_xml), review, str(reviewed))
                        digitization = verify_digitization(str(reviewed), None, str(source), resolved_score_type, omr.get("ocr_language"))
                        repaired_pdf = workdir / f"{source.stem}_omr_verified_round{round_number}.pdf"
                        repaired_render = _render(reviewed, repaired_pdf)
                        _apply_review_statuses(plan, review)
                        page_numbers = [page["page"] for page in plan.get("page_checks", []) if not _review_status_is_done(page.get("status"))]
                        page_numbers.extend(region["source_page"] for region in plan.get("regions", []) if region.get("source_page") and region["source_page"] not in page_numbers)
                        visual = prepare_visual_comparison(
                            str(source),
                            str(repaired_pdf) if repaired_render.get("passed") else None,
                            str(output_dir / "_intermediate" / f"{source.stem}_verified_visual"),
                            plan,
                            page_numbers=page_numbers or None,
                        )
                        visual["pages"] = merge_page_checks(plan.get("page_checks"), visual.get("pages"))
                        before_metric = int(plan.get("pending_page_count", 0)) + int(plan.get("unresolved_region_count", 0))
                        next_plan = build_review_plan(
                            digitization,
                            str(source),
                            plan,
                            visual_comparison=visual,
                            repair_round=round_number,
                        )
                        next_plan["patches"] = patch_result
                        next_plan["post_repair_qa"] = digitization
                        next_plan["post_repair_render"] = repaired_render
                        _apply_review_statuses(next_plan, review)
                        region_statuses = {item.get("id"): review_item_status(item) for item in review.get("regions", [])}
                        for region in next_plan.get("regions", []):
                            if region.get("id") in region_statuses and region_statuses[region["id"]] in {"verified", "repaired", "passed", "cached"}:
                                region["status"] = region_statuses[region["id"]]
                                region["repair_status"] = region_statuses[region["id"]]
                                region["verified_status"] = _review_status_is_done(region_statuses[region["id"]])
                        after_metric = int(next_plan.get("pending_page_count", 0)) + int(next_plan.get("unresolved_region_count", 0))
                        refresh_review_gate(next_plan, stagnant=not patch_result.get("applied") and after_metric >= before_metric and after_metric > 0)
                        plan = next_plan
                        current_xml = reviewed
                        if plan.get("formal_delivery") and digitization.get("passed") and patch_result.get("passed"):
                            break
                    xml_source = current_xml
                    report["qa"]["digitization"] = digitization
                elif plan["regions"] or plan["depth_repair_blocked"]:
                    plan["formal_delivery"] = False
                report["qa"]["verified_review"] = plan
            if not digitization.get("passed"):
                report["warning"] = "OMR completeness QA failed; transposition and formal delivery were blocked."
                draft_xml = output_dir / f"{source.stem}_{args.source_key.replace(' ', '_')}_to_{args.target_key.replace(' ', '_')}_DRAFT_UNVERIFIED.musicxml"
                shutil.copy2(xml_source, draft_xml)
                report["draft_outputs"].append(str(draft_xml))
                if args.format in {"pdf", "pdf-musicxml", "pdf-musicxml-lilypond"}:
                    draft_pdf = workdir / f"{draft_xml.stem}.pdf"
                    render = _render(xml_source, draft_pdf)
                    report["qa"]["draft_render"] = render
                    if render.get("passed"):
                        output_pdf = output_dir / f"{draft_xml.stem}.pdf"
                        shutil.copy2(render["output"], output_pdf)
                        report["draft_outputs"].append(str(output_pdf))
                return_code = 3
                return _finish(report, output_dir, source.stem, args.json, return_code)
        normalize = mode == "accurate" or (mode == "auto" and analysis.get("complexity") != "simple")
        if normalize:
            normalized = workdir / "normalized.musicxml"
            tree, _ = open_musicxml(str(xml_source))
            write_musicxml(tree, normalized)
            xml_source = normalized
            if source.suffix.lower() == ".pdf":
                report["qa"]["digitization_normalization"] = verify_digitization(str(xml_source), None, str(source), resolved_score_type, report["qa"]["omr"].get("ocr_language"))
        stem = source.stem
        final_stem = f"{stem}_{args.source_key.replace(' ', '_')}_to_{args.target_key.replace(' ', '_')}"
        target_xml = workdir / f"{final_stem}.musicxml"
        report["qa"]["transposition"] = transpose_file(str(xml_source), str(target_xml), args.source_key, args.target_key)
        report["qa"]["structure"] = verify_structure(str(xml_source), str(target_xml))
        report["qa"]["pitch"] = verify_pitch(str(xml_source), str(target_xml), args.source_key, args.target_key)
        report["qa"]["content_preservation"] = verify_content_preservation(str(xml_source), str(target_xml), resolved_score_type)
        render = None
        if args.format in {"pdf", "pdf-musicxml", "pdf-musicxml-lilypond"} or (mode == "verified" and source.suffix.lower() == ".pdf"):
            target_pdf = workdir / f"{final_stem}.pdf"
            render = _render(target_xml, target_pdf)
            report["qa"]["render"] = render
            if source.suffix.lower() == ".pdf" and render.get("passed"):
                report["qa"]["layout"] = verify_layout(str(source), str(target_pdf))
                if mode == "verified":
                    post_visual = prepare_visual_comparison(
                        str(source),
                        str(target_pdf),
                        str(output_dir / "_intermediate" / f"{source.stem}_post_transpose_visual"),
                        report["qa"].get("verified_review", {}),
                        cache_field="post_page_checks",
                    )
                    report["qa"]["verified_review"]["post_transpose_visual_comparison"] = post_visual
                    report["qa"]["verified_review"]["post_page_checks"] = post_visual.get("pages", [])
                    post_review = review_payload
                    if post_review is None and args.review_json:
                        post_review = load_review(args.review_json)
                    if post_review:
                        post_review = (post_review.get("rounds") or [post_review])[-1]
                        _apply_review_statuses(report["qa"]["verified_review"], post_review, field="post_page_checks")
                        post_statuses = {item.get("id"): review_item_status(item) for item in post_review.get("post_page_checks", [])}
                        for page in post_visual.get("pages", []):
                            if page.get("id") in post_statuses and _review_status_is_done(post_statuses[page["id"]]):
                                page["status"] = post_statuses[page["id"]]
                        post_pending = any(not _review_status_is_done(page.get("status")) for page in post_visual.get("pages", []))
                        report["qa"]["verified_review"]["post_transpose_visual_passed"] = not post_pending
                    else:
                        report["qa"]["verified_review"]["post_transpose_visual_passed"] = False
        checks = [report["qa"].get("transposition", {}), report["qa"].get("structure", {}), report["qa"].get("pitch", {}), report["qa"].get("content_preservation", {})]
        if mode == "verified" and source.suffix.lower() == ".pdf":
            checks.append({"passed": report["qa"].get("verified_review", {}).get("formal_delivery", False) and report["qa"].get("verified_review", {}).get("post_transpose_visual_passed", False)})
        if render is not None:
            checks.append(render)
        if report["qa"].get("layout"):
            checks.append(report["qa"]["layout"])
        ready = all(check.get("passed", False) for check in checks)
        if ready:
            output_xml = output_dir / f"{final_stem}.musicxml"
            shutil.copy2(target_xml, output_xml)
            report["outputs"].append(str(output_xml))
            if render and render.get("passed") and args.format in {"pdf", "pdf-musicxml", "pdf-musicxml-lilypond"}:
                output_pdf = output_dir / f"{final_stem}.pdf"
                shutil.copy2(render["output"], output_pdf)
                report["outputs"].append(str(output_pdf))
            if args.format == "pdf-musicxml-lilypond":
                ly = output_dir / f"{final_stem}.ly"
                subprocess.run([sys.executable, str(Path(__file__).with_name("musicxml_to_lilypond.py")), "--source", str(output_xml), "--target", str(ly)], check=False)
                if ly.exists():
                    report["outputs"].append(str(ly))
            report["passed"] = True
            report["formal_delivery"] = True
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if report["passed"]:
        report["risk"] = "low" if analysis.get("complexity") == "simple" else "medium"
    return _finish(report, output_dir, source.stem, args.json, 0 if report["passed"] else 3)


def _finish(report: dict, output_dir: Path, stem: str, as_json: bool, return_code: int) -> int:
    _write_report(report, output_dir, stem)
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("passed"):
        print("乐谱处理完成。已生成 MusicXML 和 PDF。")
    else:
        print("乐谱已完成初步处理，但未通过完整性校验，已保留草稿供 MuseScore 人工检查。")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Bounded PDF -> MusicXML digitization with OMR completeness gates."""

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
from verify_digitization import verify as verify_digitization
from verify_layout import verify as verify_layout
from verify_score_structure import summary
from verified_review import apply_review_patches, build_review_plan, load_review, merge_page_checks, prepare_visual_comparison, refresh_review_gate, review_item_status


def _render(musicxml: Path, pdf: Path) -> dict:
    rendered = subprocess.run([sys.executable, str(Path(__file__).with_name("render_output.py")), "--musicxml", str(musicxml), "--output-pdf", str(pdf), "--json"], capture_output=True, text=True)
    try:
        return json.loads(rendered.stdout)
    except json.JSONDecodeError:
        return {"passed": False, "error": "PDF rendering failed", "stderr": rendered.stderr[-2000:]}


def _normalise_mode(mode: str) -> str:
    return "verified" if mode == "high-accuracy" else mode


def _review_status_is_done(status: str | None) -> bool:
    return status in {"verified", "passed", "cached"}


def _apply_review_statuses(plan: dict, review: dict) -> None:
    page_statuses = {item.get("id"): review_item_status(item) for item in review.get("page_checks", [])}
    for page in plan.get("page_checks", []):
        if page.get("id") in page_statuses and _review_status_is_done(page_statuses[page["id"]]):
            page["status"] = page_statuses[page["id"]]
            page["page_verified"] = True
            page["visual_check"] = "completed"
    region_statuses = {item.get("id"): review_item_status(item) for item in review.get("regions", [])}
    for region in plan.get("regions", []):
        if region.get("id") in region_statuses and region_statuses[region["id"]] in {"verified", "repaired", "passed", "cached"}:
            region["status"] = region_statuses[region["id"]]
            region["repair_status"] = region_statuses[region["id"]]
            region["verified_status"] = _review_status_is_done(region_statuses[region["id"]])
    plan["pending_page_count"] = sum(not _review_status_is_done(page.get("status")) for page in plan.get("page_checks", []))
    refresh_review_gate(plan)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--format", choices=["musicxml", "musicxml-pdf"], default="musicxml-pdf")
    parser.add_argument("--mode", choices=["auto", "fast", "accurate", "verified", "high-accuracy"], default="auto", help="verified/high-accuracy enables bounded anomaly review; default modes are unchanged")
    parser.add_argument("--score-type", choices=["auto", "vocal", "instrumental"], default="auto")
    parser.add_argument("--ocr-language", default="auto")
    parser.add_argument("--review-json", help="verified mode: explicit visual-review results and local MusicXML patches")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    requested_mode = _normalise_mode(args.mode)
    mode = requested_mode
    report = {"task": "digitize", "input": str(source), "requested_mode": requested_mode, "mode": mode, "score_type": args.score_type, "ocr_language": args.ocr_language, "outputs": [], "draft_outputs": [], "intermediate_outputs": [], "qa": {}, "risk": "high", "passed": False, "formal_delivery": False}
    if source.suffix.lower() != ".pdf":
        report["error"] = "digitize mode requires a PDF input"
        return _finish(report, output_dir, source.stem, args.json, 2)
    analysis = analyze(str(source))
    report["analysis"] = analysis
    if requested_mode == "auto":
        mode = analysis.get("recommended_mode", "fast")
        report["mode"] = mode
    if analysis.get("pdf_type") == "vector":
        report["qa"]["pdf_structure"] = analysis.get("pdf_structure", {})
        report["qa"]["pdf_structure"]["omr_fallback_reason"] = "The PDF exposes vector evidence, but its graphics/text do not provide reliable MusicXML note semantics."
    workdir = Path(tempfile.mkdtemp(prefix="score-digitize-"))
    try:
        draft, omr = run_omr(source, workdir, args.score_type, args.ocr_language)
        report["qa"]["omr"] = retain_omr_logs(omr, output_dir, source.stem)
        if not draft:
            report["warning"] = "OMR did not produce a usable MusicXML file."
            return _finish(report, output_dir, source.stem, args.json, 2)
        log = omr.get("attempts", [{}])[-1].get("log") if omr.get("attempts") else None
        resolved_score_type = omr.get("score_type", args.score_type)
        report["qa"]["digitization_draft"] = verify_digitization(str(draft), log, str(source), resolved_score_type, omr.get("ocr_language"))
        qa_for_delivery = report["qa"]["digitization_draft"]
        if requested_mode == "auto":
            auto_reasons = list(analysis.get("verification_reasons", []))
            if resolved_score_type == "vocal":
                auto_reasons.append("vocal_score")
            if not qa_for_delivery.get("passed") or qa_for_delivery.get("review_candidates"):
                auto_reasons.append("omr_or_content_qa_warning")
            if auto_reasons:
                mode = "verified"
                report["mode"] = mode
                report["auto_verification_reasons"] = sorted(set(auto_reasons))

        normalize = mode in {"accurate", "verified"} or (mode == "auto" and analysis.get("complexity") != "simple")
        provisional = draft
        if normalize:
            provisional = workdir / f"{source.stem}_provisional.musicxml"
            tree, _ = open_musicxml(draft)
            write_musicxml(tree, provisional)
            report["qa"]["digitization_final"] = verify_digitization(str(provisional), None, str(source), resolved_score_type, omr.get("ocr_language"))
            report["qa"]["digitization_final"]["auto_repairs"] = ["canonical XML serialization"]
        else:
            report["qa"]["digitization_final"] = report["qa"]["digitization_draft"]

        if mode == "verified":
            previous = output_dir / f"{source.stem}_qa.json"
            cached = {}
            if previous.exists():
                try:
                    cached = json.loads(previous.read_text(encoding="utf-8")).get("qa", {}).get("verified_review", {})
                except (OSError, json.JSONDecodeError):
                    cached = {}
            visual_pdf = workdir / f"{source.stem}_verified.pdf"
            verified_render = _render(provisional, visual_pdf)
            report["qa"]["verified_render"] = verified_render
            visual = prepare_visual_comparison(
                str(source),
                str(visual_pdf) if verified_render.get("passed") else None,
                str(output_dir / "_intermediate" / f"{source.stem}_verified_visual"),
                cached,
            )
            plan = build_review_plan(report["qa"]["digitization_final"], str(source), cached, visual_comparison=visual)
            review_manifest = output_dir / f"{source.stem}_verified_review.json"
            review_manifest.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if args.review_json and not plan["depth_repair_blocked"]:
                review_payload = load_review(args.review_json)
                rounds = review_payload.get("rounds") or [review_payload]
                current_xml = provisional
                for round_number, review in enumerate(rounds, 1):
                    allowed = {region["id"] for region in plan["regions"]}
                    review = dict(review)
                    review["regions"] = [region for region in review.get("regions", []) if region.get("id") in allowed]
                    reviewed = workdir / f"{source.stem}_verified_round{round_number}.musicxml"
                    patch_result = apply_review_patches(str(current_xml), review, str(reviewed))
                    qa_for_delivery = verify_digitization(str(reviewed), None, str(source), resolved_score_type, omr.get("ocr_language"))
                    repaired_pdf = workdir / f"{source.stem}_verified_round{round_number}.pdf"
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
                        qa_for_delivery,
                        str(source),
                        plan,
                        visual_comparison=visual,
                        repair_round=round_number,
                    )
                    next_plan["patches"] = patch_result
                    next_plan["post_repair_qa"] = qa_for_delivery
                    next_plan["post_repair_render"] = repaired_render
                    _apply_review_statuses(next_plan, review)
                    after_metric = int(next_plan.get("pending_page_count", 0)) + int(next_plan.get("unresolved_region_count", 0))
                    refresh_review_gate(next_plan, stagnant=not patch_result.get("applied") and after_metric >= before_metric and after_metric > 0)
                    plan = next_plan
                    current_xml = reviewed
                    if plan.get("formal_delivery") and qa_for_delivery.get("passed") and patch_result.get("passed"):
                        break
                provisional = current_xml
            elif plan["regions"] or plan["depth_repair_blocked"]:
                plan["formal_delivery"] = False
            report["qa"]["digitization_final"] = qa_for_delivery
            report["qa"]["verified_review"] = plan
        report["qa"]["structure"] = {"source": summary(str(draft)), "target": summary(str(provisional)), "passed": summary(str(draft)) == summary(str(provisional))}
        retained = output_dir / "_intermediate" / f"{source.stem}_omr_draft{draft.suffix}"
        retained.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(draft, retained)
        report["intermediate_outputs"].append(str(retained))
        render = None
        if args.format == "musicxml-pdf" and mode != "verified":
            target_pdf = workdir / f"{source.stem}_provisional.pdf"
            render = _render(provisional, target_pdf)
            report["qa"]["render"] = render
            if render.get("passed"):
                report["qa"]["layout"] = verify_layout(str(source), str(target_pdf))
        elif mode == "verified":
            render = report["qa"].get("verified_render")
            if report["qa"].get("verified_review", {}).get("formal_delivery"):
                render = report["qa"].get("verified_review", {}).get("post_repair_render") or render
            report["qa"]["render"] = render or {"passed": False, "error": "verified rendering unavailable"}
            if render and render.get("passed"):
                report["qa"]["layout"] = verify_layout(str(source), str(render["output"]))
        checks = [qa_for_delivery, report["qa"]["digitization_final"], report["qa"]["structure"]]
        if mode == "verified":
            checks.append({"passed": report["qa"]["verified_review"].get("formal_delivery", False)})
        if render is not None:
            checks.extend([render, report["qa"].get("layout", {})])
        ready = all(check.get("passed", False) for check in checks)
        if ready:
            final_xml = output_dir / f"{source.stem}_digitized.musicxml"
            shutil.copy2(provisional, final_xml)
            report["outputs"].append(str(final_xml))
            if render and render.get("passed"):
                final_pdf = output_dir / f"{source.stem}_digitized.pdf"
                shutil.copy2(render["output"], final_pdf)
                report["outputs"].append(str(final_pdf))
            report["passed"] = True
            report["formal_delivery"] = True
        else:
            report["warning"] = "OMR completeness QA failed; only a draft is available."
            draft_xml = output_dir / f"{source.stem}_DRAFT_UNVERIFIED.musicxml"
            shutil.copy2(provisional, draft_xml)
            report["draft_outputs"].append(str(draft_xml))
            if render and render.get("passed"):
                draft_pdf = output_dir / f"{source.stem}_DRAFT_UNVERIFIED.pdf"
                shutil.copy2(render["output"], draft_pdf)
                report["draft_outputs"].append(str(draft_pdf))
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    report["risk"] = "low" if report["passed"] and not report["qa"].get("digitization_final", {}).get("review_candidates") else "medium" if report["passed"] else "high"
    return _finish(report, output_dir, source.stem, args.json, 0 if report["passed"] else 3)


def _finish(report: dict, output_dir: Path, stem: str, as_json: bool, return_code: int) -> int:
    report_path = output_dir / f"{stem}_qa.json"
    report["qa_report"] = str(report_path)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if as_json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif report.get("passed"):
        print("乐谱处理完成。已生成 MusicXML 和 PDF。")
    else:
        print("乐谱已完成初步识别，但未通过完整性校验，建议在 MuseScore 中人工校对。")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())

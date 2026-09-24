#!/usr/bin/env python3
"""Bounded Audiveris OMR with explicit vocal/OCR configuration."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

try:
    from .common import find_executable, open_musicxml
except ImportError:
    from common import find_executable, open_musicxml


LANGUAGE_ALIASES = {
    "en": "eng",
    "eng": "eng",
    "english": "eng",
    "zh": "chi_sim",
    "zh-cn": "chi_sim",
    "中文": "chi_sim",
    "简体中文": "chi_sim",
    "chinese": "chi_sim",
    "chi_sim": "chi_sim",
}
TESSDATA_BASE_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata/main/"
OCR_LOG_PATTERNS = (
    "no ocr is available",
    "tesseract data could not be found",
    "could not initialize tessbaseapi",
    "ocr link error",
)


def _contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", text))


def resolve_ocr_languages(specification: str | None, source: Path) -> list[str]:
    raw = (specification or "auto").strip()
    if not raw or raw.lower() == "auto":
        raw = "chi_sim" if _contains_cjk(source.name) else "eng"
    languages = []
    for item in raw.split("+"):
        key = item.strip().lower()
        language = LANGUAGE_ALIASES.get(key, item.strip())
        if not language or not re.fullmatch(r"[A-Za-z0-9_\-]+", language):
            raise ValueError(f"Unsupported OCR language specification: {specification!r}")
        if language not in languages:
            languages.append(language)
    return languages


def resolve_score_type(score_type: str | None, source: Path) -> str:
    value = (score_type or "auto").strip().lower()
    if value in {"vocal", "instrumental"}:
        return value
    if value != "auto":
        raise ValueError(f"Unsupported score type: {score_type!r}")
    return "instrumental"


def tessdata_folder() -> Path:
    configured = os.environ.get("TESSDATA_PREFIX")
    if configured and Path(configured).is_dir():
        return Path(configured)
    if os.name == "nt":
        return Path.home() / "AppData" / "Roaming" / "Audiveris" / "tessdata"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Audiveris" / "tessdata"
    return Path.home() / ".audiveris" / "tessdata"


def installed_ocr_languages(folder: Path) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(path.stem for path in folder.glob("*.traineddata") if path.is_file())


def _download_with_curl(curl: str, url: str, target: Path) -> None:
    probe = subprocess.run([curl, "--http1.1", "--ipv4", "--fail", "--location", "--range", "0-0", "--dump-header", "-", "--output", "/dev/null", "--max-time", "20", url], capture_output=True, text=True, timeout=30)
    ranges = re.findall(r"content-range:\s*bytes\s+\d+-\d+/(\d+)", (probe.stdout or "") + (probe.stderr or ""), re.I)
    total = int(ranges[-1]) if ranges else 0
    if total <= 0:
        result = subprocess.run([curl, "--http1.1", "--ipv4", "--fail", "--location", "--max-time", "120", "--silent", "--show-error", "--output", str(target), url], capture_output=True, text=True, timeout=150)
        if result.returncode != 0:
            raise OSError(result.stderr.strip() or f"curl exited with {result.returncode}")
        return
    chunk_size = 1 * 1024 * 1024
    chunk_path = target.with_suffix(".chunk")
    try:
        with target.open("wb") as output:
            for start in range(0, total, chunk_size):
                end = min(total - 1, start + chunk_size - 1)
                result = subprocess.run([curl, "--http1.1", "--ipv4", "--fail", "--location", "--range", f"{start}-{end}", "--max-time", "30", "--silent", "--show-error", "--output", str(chunk_path), url], capture_output=True, text=True, timeout=45)
                if result.returncode != 0:
                    raise OSError(result.stderr.strip() or f"curl exited with {result.returncode}")
                data = chunk_path.read_bytes()
                expected = end - start + 1
                if len(data) != expected:
                    raise OSError(f"unexpected OCR data chunk size: expected {expected}, got {len(data)}")
                output.write(data)
    finally:
        if chunk_path.exists():
            chunk_path.unlink()


def ensure_ocr_languages(languages: list[str], folder: Path) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    installed_before = installed_ocr_languages(folder)
    missing = [language for language in languages if language not in installed_before]
    downloaded = []
    errors = []
    for language in missing:
        target = folder / f"{language}.traineddata"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(prefix=f"{language}-", suffix=".part", dir=folder, delete=False) as handle:
                temporary = Path(handle.name)
            url = f"{TESSDATA_BASE_URL}{language}.traineddata"
            curl = shutil.which("curl")
            if curl:
                _download_with_curl(curl, url, temporary)
            else:
                urllib.request.urlretrieve(url, temporary)
            if temporary.stat().st_size == 0:
                raise OSError("downloaded OCR data is empty")
            temporary.replace(target)
            downloaded.append(language)
        except Exception as exc:
            errors.append({"language": language, "reason": str(exc)})
            if temporary and temporary.exists():
                temporary.unlink()
        except BaseException:
            if temporary and temporary.exists():
                temporary.unlink()
            raise
    installed_after = installed_ocr_languages(folder)
    return {
        "folder": str(folder),
        "requested": languages,
        "installed_before": installed_before,
        "downloaded": downloaded,
        "installed_after": installed_after,
        "missing": [language for language in languages if language not in installed_after],
        "errors": errors,
        "passed": all(language in installed_after for language in languages),
    }


def audiveris_version(audiveris: str) -> dict:
    result = subprocess.run([audiveris, "-version"], capture_output=True, text=True, timeout=30)
    text = (result.stdout or "") + "\n" + (result.stderr or "")
    version = re.search(r"- Version:\s*(.+)", text)
    ocr = re.search(r"- OCR Engine:\s*(.+)", text)
    return {
        "version": version.group(1).strip() if version else None,
        "ocr_engine": ocr.group(1).strip() if ocr else None,
        "returncode": result.returncode,
        "passed": result.returncode == 0,
    }


def build_audiveris_command(audiveris: str, output: Path, pdf: Path, score_type: str, languages: list[str], retry: bool = False) -> tuple[list[str], dict]:
    command = [audiveris, "-batch", "-export", "-output", str(output)]
    environment = os.environ.copy()
    configuration = {"lyrics_support": False, "ocr_language": None, "retry": retry}
    if score_type == "vocal":
        folder = tessdata_folder()
        environment["TESSDATA_PREFIX"] = str(folder)
        command.extend([
            "-constant", "org.audiveris.omr.text.tesseract.TesseractOCR.useOCR=true",
            "-constant", f"org.audiveris.omr.text.Language.defaultSpecification={'+'.join(languages)}",
        ])
        if retry:
            command.extend([
                "-force",
                "-constant", "org.audiveris.omr.text.tesseract.TesseractOCR.forceSingleBlock=false",
            ])
        configuration.update({"lyrics_support": True, "ocr_language": "+".join(languages), "tessdata_folder": str(folder)})
    command.append(str(pdf))
    return command, {"environment": environment, "configuration": configuration}


def _log_has_ocr_failure(log_path: Path) -> bool:
    text = log_path.read_text(errors="replace").lower() if log_path.exists() else ""
    return any(pattern in text for pattern in OCR_LOG_PATTERNS)


def _xml_quality(path: Path | None, score_type: str) -> dict:
    if path is None:
        return {"measures": 0, "notes": 0, "lyrics": 0, "severe_structure": True, "needs_retry": True}
    try:
        tree, _ = open_musicxml(path)
        root = tree.getroot()
        measures = root.findall(".//part/measure")
        lyrics = root.findall(".//lyric")
        notes = root.findall(".//note")
        severe = not root.findall("part") or not measures or not notes
        return {"measures": len(measures), "notes": len(notes), "lyrics": len(lyrics), "severe_structure": severe, "needs_retry": score_type == "vocal" and (not lyrics or severe)}
    except (OSError, ValueError):
        return {"measures": 0, "notes": 0, "lyrics": 0, "severe_structure": True, "needs_retry": True}


def _run_audiveris_once(audiveris: str, pdf: Path, output: Path, score_type: str, languages: list[str], retry: bool) -> tuple[Path | None, dict]:
    output.mkdir(parents=True, exist_ok=True)
    command, settings = build_audiveris_command(audiveris, output, pdf, score_type, languages, retry)
    result = subprocess.run(command, capture_output=True, text=True, timeout=300, env=settings["environment"])
    log_path = output / "audiveris.log"
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    candidates = sorted(output.glob("*.mxl")) + sorted(output.glob("*.musicxml")) + sorted(output.glob("*.xml"))
    xml = candidates[0] if result.returncode == 0 and candidates else None
    attempt = {"tool": "audiveris", "returncode": result.returncode, "log": str(log_path), "stderr": result.stderr[-3000:], "retry": retry, "configuration": settings["configuration"], "quality": _xml_quality(xml, score_type), "ocr_failure": _log_has_ocr_failure(log_path)}
    attempt["needs_retry"] = bool(attempt["quality"].get("needs_retry") or attempt["ocr_failure"])
    return xml, attempt


def _run_homr_once(pdf: Path, workdir: Path) -> tuple[Path | None, dict]:
    homr = find_executable("homr")
    if not homr:
        return None, {"tool": "homr", "skipped": True, "reason": "not installed"}
    homr_dir = workdir / "homr"
    homr_dir.mkdir(parents=True, exist_ok=True)
    pdftoppm = find_executable("pdftoppm")
    homr_inputs = []
    if pdftoppm:
        converted = subprocess.run([pdftoppm, "-png", "-r", "200", str(pdf), str(homr_dir / "page")], capture_output=True, text=True, timeout=180)
        homr_inputs = sorted(homr_dir.glob("page-*.png")) if converted.returncode == 0 else []
    if not homr_inputs:
        input_copy = homr_dir / pdf.name
        shutil.copy2(pdf, input_copy)
        homr_inputs = [input_copy]
    result = subprocess.run([homr, *(str(path) for path in homr_inputs)], cwd=homr_dir, capture_output=True, text=True, timeout=600)
    candidates = sorted(homr_dir.glob("*.mxl")) + sorted(homr_dir.glob("*.musicxml")) + sorted(homr_dir.glob("*.xml"))
    log_path = homr_dir / "homr.log"
    log_path.write_text((result.stdout or "") + "\n" + (result.stderr or ""), encoding="utf-8")
    return (candidates[0] if result.returncode == 0 and candidates else None), {"tool": "homr", "returncode": result.returncode, "log": str(log_path), "stderr": result.stderr[-3000:]}


def retain_omr_logs(omr: dict, output_dir: Path, stem: str) -> dict:
    debug_dir = output_dir / "_debug" / stem
    for index, attempt in enumerate(omr.get("attempts", []), 1):
        log = attempt.get("log")
        if log and Path(log).exists():
            debug_dir.mkdir(parents=True, exist_ok=True)
            retained = debug_dir / f"attempt-{index}-{attempt.get('tool', 'omr')}.log"
            shutil.copy2(log, retained)
            attempt["log"] = str(retained)
    return omr


def run_omr(pdf: Path, workdir: Path, score_type: str = "instrumental", ocr_language: str = "auto") -> tuple[Path | None, dict]:
    score_type = resolve_score_type(score_type, pdf)
    languages = resolve_ocr_languages(ocr_language, pdf) if score_type == "vocal" else []
    version = None
    attempts = []
    audiveris = find_executable("audiveris")
    if audiveris:
        version = audiveris_version(audiveris)
        ocr_setup = ensure_ocr_languages(languages, tessdata_folder()) if score_type == "vocal" else {"requested": [], "installed_after": [], "missing": [], "passed": True}
        if not ocr_setup["passed"]:
            return None, {"passed": False, "engine": "audiveris", "score_type": score_type, "ocr_language": "+".join(languages) if languages else None, "audiveris": version, "ocr_setup": ocr_setup, "attempts": attempts, "error": "Required OCR language data is unavailable"}
        xml, attempt = _run_audiveris_once(audiveris, pdf, workdir / "audiveris-attempt-1", score_type, languages, retry=False)
        attempts.append(attempt)
        if xml and not attempt["needs_retry"]:
            return xml, {"passed": True, "engine": "audiveris", "score_type": score_type, "ocr_language": "+".join(languages) if languages else None, "audiveris": version, "ocr_setup": ocr_setup, "attempts": attempts}
        if score_type == "vocal":
            xml_retry, retry_attempt = _run_audiveris_once(audiveris, pdf, workdir / "audiveris-attempt-2", score_type, languages, retry=True)
            attempts.append(retry_attempt)
            if xml_retry:
                return xml_retry, {"passed": True, "engine": "audiveris", "score_type": score_type, "ocr_language": "+".join(languages), "audiveris": version, "ocr_setup": ocr_setup, "attempts": attempts, "retried": True}
    if score_type != "vocal":
        xml, attempt = _run_homr_once(pdf, workdir)
        attempts.append(attempt)
        if xml:
            return xml, {"passed": True, "engine": "homr", "score_type": score_type, "ocr_language": None, "audiveris": version, "attempts": attempts}
    error = "Audiveris failed after the allowed OMR attempts" if audiveris else "No usable OMR engine is available"
    return None, {"passed": False, "engine": "audiveris" if audiveris else None, "score_type": score_type, "ocr_language": "+".join(languages) if languages else None, "audiveris": version, "attempts": attempts, "error": error}

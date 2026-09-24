import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.omr import build_audiveris_command, installed_ocr_languages, resolve_ocr_languages, run_omr


class OMRConfigurationTests(unittest.TestCase):
    def test_chinese_filename_selects_simplified_chinese(self):
        source = Path("青主-大江东去.pdf")
        self.assertEqual(resolve_ocr_languages("auto", source), ["chi_sim"])

    def test_vocal_command_uses_supported_audiveris_constants(self):
        with patch("scripts.omr.tessdata_folder", return_value=Path("/tmp/tessdata")):
            command, settings = build_audiveris_command("audiveris", Path("/tmp/out"), Path("score.pdf"), "vocal", ["eng"])
        self.assertIn("-constant", command)
        self.assertIn("org.audiveris.omr.text.tesseract.TesseractOCR.useOCR=true", command)
        self.assertIn("org.audiveris.omr.text.Language.defaultSpecification=eng", command)
        self.assertTrue(settings["configuration"]["lyrics_support"])

    def test_installed_languages_are_read_from_tessdata(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "eng.traineddata").write_bytes(b"test")
            self.assertEqual(installed_ocr_languages(folder), ["eng"])

    def test_vocal_omr_retries_once_after_missing_lyrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "first.musicxml"
            second = root / "second.musicxml"
            attempts = [
                (first, {"tool": "audiveris", "needs_retry": True, "quality": {"lyrics": 0}}),
                (second, {"tool": "audiveris", "needs_retry": False, "quality": {"lyrics": 4}}),
            ]
            with patch("scripts.omr.find_executable", return_value="audiveris"), patch("scripts.omr.audiveris_version", return_value={"version": "5.11.0"}), patch("scripts.omr.ensure_ocr_languages", return_value={"requested": ["chi_sim"], "installed_after": ["chi_sim"], "missing": [], "passed": True}), patch("scripts.omr._run_audiveris_once", side_effect=attempts) as run:
                xml, report = run_omr(Path("青主-大江东去.pdf"), root / "work", "vocal", "chi_sim")
            self.assertEqual(xml, second)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(len(report["attempts"]), 2)


if __name__ == "__main__":
    unittest.main()

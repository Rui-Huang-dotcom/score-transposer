import tempfile
import unittest
from pathlib import Path

from scripts.verify_digitization import verify
from scripts.verify_digitization import inspect_musicxml, verify_content_preservation


SCORE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths><mode>major</mode></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type></note></measure></part></score-partwise>'''


class DigitizationQATests(unittest.TestCase):
    def test_clean_draft_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / "score.musicxml"
            score.write_text(SCORE_XML, encoding="utf-8")
            result = verify(str(score))
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["inspection"]["measures"], 1)

    def test_omr_rhythm_diagnostic_blocks_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / "score.musicxml"
            log = Path(directory) / "audiveris.log"
            score.write_text(SCORE_XML, encoding="utf-8")
            log.write_text("Time inconsistency in measure 7\n", encoding="utf-8")
            result = verify(str(score), str(log), "source.pdf")
            self.assertFalse(result["passed"])
            self.assertTrue(result["repair_required"])
            self.assertEqual(result["omr_diagnostics"][0]["pattern"], "time inconsistency")

    def test_vocal_score_without_lyrics_blocks_formal_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / "score.musicxml"
            score.write_text(SCORE_XML.replace("<part-name>Voice</part-name>", "<part-name>Voice</part-name>"), encoding="utf-8")
            result = verify(str(score), score_type="vocal", ocr_language="chi_sim")
            self.assertFalse(result["passed"])
            self.assertFalse(result["formal_delivery"])
            self.assertEqual(result["inspection"]["lyrics"], 0)
            self.assertIn("Vocal score detected but no lyrics were exported", result["inspection"]["warnings"])

    def test_content_summary_counts_vocal_notation(self):
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / "score.musicxml"
            score.write_text(SCORE_XML.replace(
                "</note></measure>",
                "<lyric><text>la</text><syllabic>single</syllabic></lyric></note></measure>",
            ), encoding="utf-8")
            inspection = inspect_musicxml(str(score), score_type="vocal", ocr_language="eng")
            self.assertEqual(inspection["lyrics"], 1)
            self.assertEqual(inspection["lyric_syllables"], 1)
            self.assertIn("dynamics", inspection)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts.analyze_score import analyze
from scripts.common import open_musicxml
from scripts.verified_review import apply_review_patches, build_review_plan, refresh_review_gate
from scripts.verify_digitization import inspect_musicxml


SCORE_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0"><part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions><key><fifths>0</fifths><mode>major</mode></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes><note><pitch><step>C</step><octave>4</octave></pitch><duration>4</duration><voice>1</voice><type>whole</type></note></measure></part></score-partwise>'''


class VerifiedReviewTests(unittest.TestCase):
    def test_review_plan_caps_active_regions_without_immediate_stop(self):
        qa = {
            "inspection": {
                "score_type": "vocal",
                "lyrics": 0,
                "duration_errors": 1,
                "rhythm_issues": [{"part": "P1", "measure": "1"}],
                "empty_measures": [],
                "suspicious_measures": [],
            },
            "omr_diagnostics": [
                {"text": f"ERROR accidental anomaly {index}", "location": {"page": index, "system_or_stack": 1}}
                for index in range(1, 10)
            ],
        }
        plan = build_review_plan(qa, "score.pdf")
        self.assertEqual(len(plan["regions"]), 8)
        self.assertFalse(plan["depth_repair_blocked"])
        self.assertEqual(plan["skipped_region_count"], 3)
        self.assertEqual(plan["max_active_regions"], 8)

    def test_musicxml_with_lyrics_stays_on_direct_route(self):
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / "vocal.musicxml"
            score.write_text(SCORE_XML.replace(
                "</note></measure>", "<lyric><text>la</text></lyric></note></measure>",
            ), encoding="utf-8")
            result = analyze(str(score))
            self.assertEqual(result["score_type"], "vocal")
            self.assertEqual(result["recommended_mode"], "fast")
            self.assertIn("lyrics_present", result["verification_reasons"])

    def test_related_diagnostics_share_one_page_system_region(self):
        qa = {
            "inspection": {"score_type": "instrumental", "lyrics": 0},
            "omr_diagnostics": [
                {"text": text, "location": {"page": 2, "system_or_stack": 3}}
                for text in ("duration mismatch", "clef missing", "slur missing", "dynamic missing")
            ],
        }
        plan = build_review_plan(qa, "score.pdf")
        self.assertEqual(len(plan["regions"]), 1)
        self.assertEqual(plan["regions"][0]["id"], "page:2:system:3")
        self.assertGreaterEqual(len(plan["regions"][0]["reasons"]), 3)

    def test_structure_repair_patches_cover_common_verified_findings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.musicxml"
            target = root / "target.musicxml"
            source.write_text(SCORE_XML, encoding="utf-8")
            result = apply_review_patches(
                str(source),
                {
                    "regions": [{
                        "id": "part:P1:measure:1",
                        "status": "repaired",
                        "patches": [
                            {"op": "set-note-duration", "part": "P1", "measure": "1", "note_index": 1, "duration": 2},
                            {"op": "set-tuplet", "part": "P1", "measure": "1", "note_index": 1, "actual_notes": 3, "actual_type": "eighth", "normal_notes": 2, "normal_type": "eighth"},
                            {"op": "set-clef", "part": "P1", "measure": "1", "sign": "F", "line": 4},
                            {"op": "set-octave-shift", "part": "P1", "measure": "1", "type": "up", "size": 8},
                            {"op": "set-slur", "part": "P1", "measure": "1", "note_index": 1, "type": "start"},
                            {"op": "set-tie", "part": "P1", "measure": "1", "note_index": 1, "type": "start"},
                            {"op": "set-articulation", "part": "P1", "measure": "1", "note_index": 1, "value": "staccato"},
                            {"op": "set-dynamics", "part": "P1", "measure": "1", "value": "mf"},
                        ],
                    }],
                },
                str(target),
            )
            self.assertTrue(result["passed"], result)
            tree, _ = open_musicxml(target)
            self.assertEqual(tree.findtext(".//note/duration"), "2")
            self.assertIsNotNone(tree.find(".//time-modification"))
            self.assertEqual(tree.findtext(".//clef/sign"), "F")
            self.assertIsNotNone(tree.find(".//octave-shift"))
            self.assertIsNotNone(tree.find(".//notations/slur"))
            self.assertIsNotNone(tree.find(".//tie"))
            self.assertIsNotNone(tree.find(".//articulations/staccato"))
            self.assertIsNotNone(tree.find(".//dynamics/mf"))

    def test_second_round_stops_only_with_unresolved_findings(self):
        plan = build_review_plan({"inspection": {"score_type": "instrumental"}}, "score.pdf", visual_comparison={"status": "page_pairs_prepared", "pages": [{"id": "page:1", "status": "pending"}]})
        plan["repair_round"] = 2
        plan["page_checks"][0]["status"] = "pending"
        refresh_review_gate(plan, stagnant=True)
        self.assertTrue(plan["depth_repair_blocked"])
        self.assertFalse(plan["formal_delivery"])

    def test_explicit_lyric_patch_is_local(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.musicxml"
            target = root / "target.musicxml"
            source.write_text(SCORE_XML, encoding="utf-8")
            result = apply_review_patches(
                str(source),
                {
                    "regions": [{
                        "id": "lyrics_missing:?:?:?:?",
                        "status": "repaired",
                        "patches": [{"op": "set-lyric", "part": "P1", "measure": "1", "note_index": 1, "text": "la"}],
                    }],
                },
                str(target),
            )
            self.assertTrue(result["passed"], result)
            self.assertEqual(inspect_musicxml(str(target), score_type="vocal")["lyrics"], 1)


if __name__ == "__main__":
    unittest.main()

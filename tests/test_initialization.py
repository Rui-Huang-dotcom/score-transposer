import unittest

from scripts.initialize_environment import missing_system
from scripts.install_dependencies import commands_for


class InitializationTests(unittest.TestCase):
    def test_all_system_dependencies_are_reported_together(self):
        snapshot = {"commands": {name: {"available": False} for name in ("python", "lilypond", "audiveris", "musescore", "pdfinfo", "pdftoppm")}}
        self.assertEqual(missing_system(snapshot), ["python", "audiveris", "musescore", "poppler"])

    def test_complete_snapshot_has_no_missing_system_dependencies(self):
        snapshot = {"commands": {name: {"available": True} for name in ("python", "lilypond", "audiveris", "musescore", "pdfinfo", "pdftoppm")}}
        self.assertEqual(missing_system(snapshot), [])

    def test_lilypond_is_optional_because_musescore_is_the_primary_renderer(self):
        self.assertNotIn("lilypond", missing_system({"commands": {"python": {"available": True}, "audiveris": {"available": True}, "musescore": {"available": True}, "pdfinfo": {"available": True}, "pdftoppm": {"available": True}, "lilypond": {"available": False}}}))
        self.assertIn("python", commands_for("Darwin"))


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path

from scripts.common import open_musicxml
from scripts.transpose_musicxml import transpose_file
from scripts.verify_pitch import verify as verify_pitch
from scripts.verify_score_structure import verify as verify_structure
from scripts.verify_digitization import verify_content_preservation


SCORE = '''<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Voice</part-name></score-part></part-list>
  <part id="P1">
    <measure number="1">
      <attributes><divisions>1</divisions><key><fifths>2</fifths><mode>major</mode></key><time><beats>4</beats><beat-type>4</beat-type></time><clef><sign>G</sign><line>2</line></clef></attributes>
      <note><pitch><step>D</step><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type><lyric><text>la</text></lyric></note>
      <note><pitch><step>F</step><alter>1</alter><octave>4</octave></pitch><duration>1</duration><voice>1</voice><type>quarter</type></note>
      <note><rest/><duration>2</duration><voice>1</voice><type>half</type></note>
    </measure>
  </part>
</score-partwise>'''


class MusicXMLTests(unittest.TestCase):
    def test_d_major_to_b_flat_major_preserves_structure_and_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.musicxml"
            target = Path(directory) / "target.musicxml"
            source.write_text(SCORE, encoding="utf-8")
            result = transpose_file(str(source), str(target), "D major", "Bb major")
            self.assertTrue(result["passed"], result)
            self.assertEqual(result["semitones"], -4)
            self.assertTrue(verify_structure(str(source), str(target))["passed"])
            pitch = verify_pitch(str(source), str(target), "D major", "Bb major")
            self.assertTrue(pitch["passed"], pitch)
            tree, _ = open_musicxml(target)
            self.assertEqual(tree.findtext(".//pitch/step"), "B")
            content = verify_content_preservation(str(source), str(target))
            self.assertTrue(content["passed"], content)

    def test_transposing_instrument_requires_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clarinet.musicxml"
            target = Path(directory) / "target.musicxml"
            source.write_text(SCORE.replace("<clef>", "<transpose><diatonic>1</diatonic><chromatic>2</chromatic></transpose><clef>"), encoding="utf-8")
            with self.assertRaises(ValueError):
                transpose_file(str(source), str(target), "D major", "Bb major")


if __name__ == "__main__":
    unittest.main()

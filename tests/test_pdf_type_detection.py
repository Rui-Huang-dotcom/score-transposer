import tempfile
import unittest
from pathlib import Path

from scripts.analyze_score import pdf_structure


class PdfTypeDetectionTests(unittest.TestCase):
    def test_large_page_images_without_fonts_use_scan_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scan.pdf"
            path.write_bytes(b"%PDF-1.7\n/Subtype /Image /Width 2498 /Height 3456\n")
            result = pdf_structure(path)
            self.assertEqual(result["pdf_type"], "scan")
            self.assertTrue(result["page_sized_raster_evidence"])

    def test_font_evidence_without_page_image_uses_vector_route(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vector.pdf"
            path.write_bytes(b"%PDF-1.7\n/Type /Font /FontFile2 3 0 R\nBT /F1 12 Tf (Title) Tj ET\n")
            result = pdf_structure(path)
            self.assertEqual(result["pdf_type"], "vector")
            self.assertFalse(result["semantic_structure_available"])


if __name__ == "__main__":
    unittest.main()

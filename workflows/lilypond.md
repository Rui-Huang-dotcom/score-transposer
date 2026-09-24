# LilyPond route

Use only for simple, structured material whose notes, rhythms, clefs, lyrics, and key can be reconstructed with confidence. Create or retain a `.ly` source, run LilyPond, and inspect the generated PDF. The bundled `musicxml_to_lilypond.py` is intentionally conservative: chords, polyphonic timing, uncommon durations, and detailed engraving can be simplified and must be reported for manual review.

Do not use a pixel translation of a PDF as a substitute for a LilyPond source. If the input is a scanned PDF, semantic recognition still requires an OMR step first.

# Digitize workflow

1. Confirm the request is PDF → editable MusicXML and preserve the original key/pitches. If the request names a vocal score, song, lyrics, or vocal part, pass `--score-type vocal` and select `chi_sim` or `eng` as appropriate.
2. Use `analyze_score.py` for page/complexity and PDF-type detection. It uses embedded fonts, text/drawing operators, and page-sized image objects as lightweight evidence. Mixed or insufficient evidence takes the conservative scan route.
3. For vector PDFs, preserve the structure analysis as QA evidence. Do not treat PDF glyph coordinates as MusicXML or move PDF graphics to simulate semantic music changes. If that evidence cannot establish note semantics, use Audiveris as a fallback. For scans, use Audiveris; vocal mode allows at most one OCR-focused retry. Do not run two full engines in parallel or merge candidates.
4. Run `verify_digitization.py` for parse, parts/measures, notes/rests, lyrics/syllables, dynamics, slurs, ties, tuplets, articulations, clef, key, meter, durations, empty/suspicious measures, voice-conflict diagnostics, and OMR error markers. In vocal mode, zero lyrics is a critical failure.
5. In standard mode, canonicalize the XML at most once and re-run basic QA. Do not use visual repair.
6. In detailed mode, compare every source page with the current MuseScore render. Group related findings by page/system and apply local MusicXML/MuseScore structure patches for lyrics, duration/rhythm, tuplets, clefs, octave shifts, accidentals, slurs/ties, dynamics, and articulations.
7. After every repair round, re-run QA and MuseScore rendering. Recheck only modified pages/systems/measures; pages marked `page_verified` and regions marked `verified` are skipped. Continue until no new material error, no safe automatic repair remains, or one complete round produces no material improvement. Never enter an open-ended screenshot loop.
8. Render with MuseScore when requested. A parseable XML without a successful renderer is not a formal result. For transpose, compare the pre/post content summary independently from pitch and structure verification.
9. If all musical, content-preservation, and (when enabled) verified-review checks pass, write the formal output and a compact QA JSON. Otherwise write only `*_DRAFT_UNVERIFIED.musicxml` and, when rendering succeeds, a draft PDF. Never promote an OMR result with missing vocal lyrics to formal delivery.

The original PDF remains the visual reference. Detailed review uses source/rendered page pairs and local crops; it does not move PDF/JPG pixels or reconstruct a replacement scan.

For PDF transpose, perform the same bounded comparison after the final transposed MusicXML is rendered. Keep OMR-stage and post-transpose page statuses separate so a page accepted before transposition is not silently treated as checked afterward.

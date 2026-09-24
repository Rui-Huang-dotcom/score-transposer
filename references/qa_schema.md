# JSON report fields

Reports are intentionally plain JSON so a Codex task can summarize them without depending on a Python package.

- `passed`: delivery gate; false means do not announce completion or present a final-named MusicXML.
- `risk`: `low`, `medium`, or `high`.
- `analysis`: input kind, counts, route, and flags.
- `outputs`: absolute paths of verified final files only.
- `draft_outputs`: `*_DRAFT_UNVERIFIED` paths retained for debugging or manual review; never present these as a completed result.
- `intermediate_outputs`: retained drafts such as raw OMR; these are not verified deliverables.
- `qa.transposition`: note conversion count and unresolved semantic issues.
- `qa.structure`: parts, measures, noteheads, chord tones, rests, voices, staves, clefs, keys, time signatures, lyrics, ties, and duration comparisons.
- `qa.pitch`: expected semitone interval, verified/total count, and locations of mismatches.
- `qa.layout`: source/target PDF page counts. A page-count change is a review flag, not proof of a musical error.
- `qa.omr`: selected OMR engine and bounded attempt logs; raw tool diagnostics remain debug-only.
- `qa.digitization_draft` / `qa.digitization_final`: OMR diagnostics, invalid musical elements, one safe normalization if used, and visual-review candidates. Any unresolved critical item blocks a completed digitization claim.
- `qa.digitization_draft.inspection` / `qa.digitization_final.inspection`: `score_type`, `ocr_language`, `measures`, `note_elements`, `notes`, `rests`, `lyrics`, `lyric_syllables`, `dynamics`, `slurs`, `ties`, `tuplets`, `time_modifications`, `articulations`, `key_signatures`, `time_signatures`, `clefs`, `duration_errors`, `empty_measures`, `suspicious_measures`, and warnings. For vocal mode, `lyrics == 0` is critical.
- `qa.content_preservation`: independent pre/post-transposition counts and differences for lyrics, notation, structure, notes, and rests. It is separate from pitch verification.
- `formal_delivery`: false whenever OMR completeness, musical correctness, rendering, or content preservation fails.
- `qa.render`: MuseScore PDF rendering gate. `qa.layout` is added when a source PDF is available.
- `qa.verified_review`: source-PDF versus MuseScore-rendered page comparison, cached OMR-stage and post-transpose page/region statuses, selected local repair regions, repair round number, progress/stagnation state, and the final delivery gate. A detailed result is formal only when all selected pages/regions are confirmed and the musical/content QA also passes.
- Internal review input may contain a finite `rounds` array. Each entry records page/system/measure, issue type, repair status, verified status, and local MusicXML patches; each round is applied, re-checked, and rendered before the next entry is considered.
- `qa.visual_review`: legacy/debug image extraction only; it is not the formal verified gate.
- `initialization`: first-use status, marker path, system dependency snapshot, and optional fallback dependency snapshot.

Locations should use part and measure identifiers whenever the source format provides them. Preserve the full report with each recorded fixture run.

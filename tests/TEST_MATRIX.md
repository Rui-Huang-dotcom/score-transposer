# First-version test matrix

The matrix is deliberately explicit: “pending” means the fixture has not been validated and must not be presented as supported.

| Case | Fixture family | Status |
|---|---|---|
| Simple vocal | vocal | passed with `tests/fixtures/simple_vocal.musicxml` and a generated PDF round-trip |
| Vocal + piano | vocal | passed with existing `An_die_Musik.mxl` integration |
| Six-page complex vocal | vocal | pending fixture |
| Piano solo | piano | pending fixture |
| Violin + piano | instrumental | pending fixture |
| Flute | instrumental | pending fixture |
| B-flat clarinet | transposing_instruments | confirmation-gate unit tested; pitch mode pending |
| Clef changes | instrumental | structure analyzer supports detection; fixture pending |
| Dense accidentals | instrumental | semantic transformer tested for ordinary alters; fixture pending |
| Extreme high/low register | instrumental | range-preserving algorithm path exists; fixture pending |

Each promoted fixture should retain input reference, outputs, QA JSON, uncertain locations, and repair notes under its family’s `runs/<id>/` directory.

## Digitize matrix

| Case | Status |
|---|---|
| Clear scanned vocal score | passed with generated simple PDF round-trip |
| Photocopy vocal + piano | pending PDF/OMR fixture |
| Six-page complex score | pending PDF/OMR fixture |
| Piano solo | pending PDF/OMR fixture |
| Multiple voices | synthetic QA gate tested; PDF fixture pending |
| Dense accidentals | synthetic semantic path tested; PDF fixture pending |
| Clef changes | analyzer path exists; PDF fixture pending |
| Extreme ledger lines | pending PDF/OMR fixture |
| Lyrics | XML preservation + vocal zero-lyrics gate tested; real Chinese PDF blocked before OMR when `chi_sim` data is unavailable |
| Deliberately bad OMR | diagnostic gate unit tested with rhythm error |

## Vocal PDF regression

`青主-大江东去（原调）.pdf` is retained outside the Skill fixture tree. The post-change diagnostic run is under `outputs/青主-大江东去_qa_final/`; the vocal preflight run records missing `chi_sim` data under `outputs/青主-大江东去_qa_regression2/`.

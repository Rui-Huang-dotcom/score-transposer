# First integration run

On the first use, initialize once:

```bash
python3 scripts/initialize_environment.py --json
```

Use an existing structured fixture before attempting a scanned PDF. For a PDF-only digitization request, use:

```bash
python3 scripts/score_transposer.py \
  --input /Users/huangrui/Desktop/music/An_die_Musik.mxl \
  --source-key "D major" \
  --target-key "Bb major" \
  --output-dir /tmp/score-transposer-first-run \
  --format pdf-musicxml \
  --mode accurate \
  --json
```

python3 scripts/digitize_score.py --input score.pdf --output-dir outputs --format musicxml-pdf --mode accurate --json

The current machine lacks Audiveris and MuseScore, so PDF digitization is reported as blocked until those dependencies are authorized and installed. A structured MusicXML fixture can still exercise the shared semantic QA and transpose path.

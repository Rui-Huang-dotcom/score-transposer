# Existing workspace integration

Input: `/Users/huangrui/Desktop/music/An_die_Musik.mxl` (existing vocal+piano structured fixture)

Command:

```bash
python3 scripts/score_transposer.py --input /Users/huangrui/Desktop/music/An_die_Musik.mxl --source-key "D major" --target-key "Bb major" --output-dir tests/vocal/runs/first-integration --format musicxml --mode accurate --json
```

The source PDF is not copied into the Skill. See `qa.json` for the preserved absolute input reference and final checks.

# One-time dependency initialization

1. Check for `.score-transposer-initialized` in the Skill directory.
2. If absent, run `initialize_environment.py --json`. This is the only complete dependency check for the normal lifecycle.
3. If the report lists missing required dependencies, present the complete list once. Explain that Python/Audiveris/MuseScore/Poppler cover recognition, digitization, transposition, and output. Ask for one authorization covering the full list. LilyPond and HOMR are optional fallbacks and must not block normal initialization.
4. After authorization, run `initialize_environment.py --confirm-install --json`. The script installs required system dependencies through the platform package manager, rechecks them, and writes the marker only on success. The runtime uses Python's standard library; there is no separate music21/lxml/Pillow package gate.
5. If the marker exists, skip the complete check. Do not repeat installation prompts.
6. If a concrete dependency invocation later fails, run `check_dependencies.py --only DEPENDENCY`, report the failure, and repair only that dependency. Use `--force` on initialization only for an intentional full reinitialization.

The marker is a JSON state record, not a secret. It records paths, versions, platform, and initialization time. It must never be written before all required system tools pass verification.

#!/usr/bin/env python3
"""Shared MusicXML and key utilities for score-transposer."""

from __future__ import annotations

import re
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

STEP_TO_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
LETTER_INDEX = {letter: i for i, letter in enumerate("CDEFGAB")}
MAJOR_KEYS = {
    -7: ("C", -1), -6: ("G", -1), -5: ("D", -1), -4: ("A", -1),
    -3: ("E", -1), -2: ("B", -1), -1: ("F", 0), 0: ("C", 0),
    1: ("G", 0), 2: ("D", 0), 3: ("A", 0), 4: ("E", 0),
    5: ("B", 0), 6: ("F", 1), 7: ("C", 1),
}
MINOR_KEYS = {
    -7: ("A", -1), -6: ("E", -1), -5: ("B", -1), -4: ("F", 0),
    -3: ("C", 0), -2: ("G", 0), -1: ("D", 0), 0: ("A", 0),
    1: ("E", 0), 2: ("B", 0), 3: ("F", 1), 4: ("C", 1),
    5: ("G", 1), 6: ("D", 1), 7: ("A", 1),
}
KNOWN_EXECUTABLES = {
    "audiveris": ["/Applications/Audiveris.app/Contents/MacOS/audiveris"],
    "musescore": ["/Applications/MuseScore 4.app/Contents/MacOS/mscore", "/Applications/MuseScore 3.app/Contents/MacOS/mscore"],
}


def find_executable(*names: str) -> str | None:
    candidates = list(names)
    for name in names:
        candidates.extend(KNOWN_EXECUTABLES.get(name, []))
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            return path
        if Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


@dataclass(frozen=True)
class Key:
    root: str
    mode: str
    fifths: int

    @property
    def tonic_pc(self) -> int:
        accidental = 1 if self.root.endswith("#") else -1 if self.root.endswith("b") else 0
        return (STEP_TO_PC[self.root[0]] + accidental) % 12

    @property
    def tonic_letter(self) -> str:
        return self.root[0]


def _normalise_key_text(value: str) -> str:
    value = value.strip().replace("♭", "b").replace("♯", "#")
    value = value.replace("𝄫", "bb").replace("𝄪", "##")
    return re.sub(r"\s+", " ", value)


def parse_key(value: str) -> Key:
    text = _normalise_key_text(value)
    match = re.fullmatch(r"([A-Ga-g])([#b]{0,2})\s*(major|minor|maj|min|m)?", text, re.I)
    if not match:
        raise ValueError(f"Unsupported key: {value!r}; use e.g. 'D major' or 'Bb minor'")
    root = match.group(1).upper() + match.group(2)
    if len(match.group(2)) > 1:
        raise ValueError(f"Double-accidental key signatures are not supported safely: {value!r}")
    mode = "minor" if (match.group(3) or "major").lower() in {"minor", "min", "m"} else "major"
    table = MINOR_KEYS if mode == "minor" else MAJOR_KEYS
    canonical = {letter + ("#" if accidental == 1 else "b" if accidental == -1 else ""): fifths for fifths, (letter, accidental) in table.items()}
    if root in canonical:
        fifths = canonical[root]
    else:
        raise ValueError(f"Unsupported key spelling: {value!r}")
    return Key(root, mode, fifths)


def key_from_fifths(fifths: int, mode: str) -> Key:
    table = MAJOR_KEYS if mode == "major" else MINOR_KEYS
    if fifths not in table:
        raise ValueError(f"MusicXML key signature outside supported range: {fifths}")
    letter, accidental = table[fifths]
    root = letter + ("#" if accidental == 1 else "b" if accidental == -1 else "")
    return Key(root, mode, fifths)


def key_interval(source: Key, target: Key) -> tuple[int, int]:
    """Return signed chromatic semitones and spelling-compatible diatonic steps."""
    raw = (target.tonic_pc - source.tonic_pc) % 12
    semitones = raw if raw <= 6 else raw - 12
    letter_delta = (LETTER_INDEX[target.tonic_letter] - LETTER_INDEX[source.tonic_letter]) % 7
    candidates = [n for n in range(-6, 7) if n % 7 == letter_delta]
    signed = [n for n in candidates if semitones == 0 or (n > 0) == (semitones > 0)]
    pool = signed or candidates
    return semitones, min(pool, key=lambda n: abs(n - semitones / 2))


def open_musicxml(path: str | Path) -> tuple[ET.ElementTree, str]:
    path = Path(path)
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as archive:
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = next((e.get("full-path") for e in container.iter() if e.tag.endswith("rootfile")), None)
            if not rootfile:
                raise ValueError("MXL container has no rootfile")
            root = ET.fromstring(archive.read(rootfile))
            strip_namespaces(root)
            return ET.ElementTree(root), rootfile
    if path.suffix.lower() not in {".musicxml", ".xml"}:
        raise ValueError(f"Not a MusicXML/MXL file: {path}")
    tree = ET.parse(path)
    strip_namespaces(tree.getroot())
    return tree, path.name


def strip_namespaces(root: ET.Element) -> None:
    for element in root.iter():
        if "}" in element.tag:
            element.tag = element.tag.rsplit("}", 1)[1]


def write_musicxml(tree: ET.ElementTree, path: str | Path) -> None:
    ET.indent(tree, space="  ")
    tree.write(Path(path), encoding="utf-8", xml_declaration=True)


def iter_notes(root: ET.Element):
    for part in root.findall("part"):
        part_id = part.get("id", "?")
        for measure in part.findall("measure"):
            index = 0
            for note in measure.findall("note"):
                if note.find("pitch") is not None:
                    index += 1
                    yield part_id, measure.get("number", "?"), index, note


def pitch_midi(pitch: ET.Element) -> float:
    step = pitch.findtext("step")
    octave = int(pitch.findtext("octave"))
    alter = float(pitch.findtext("alter", "0"))
    return 12 * (octave + 1) + STEP_TO_PC[step] + alter


def score_has_transposition(root: ET.Element) -> bool:
    return root.find(".//transpose") is not None


def safe_int(value: str | None, default: int = 0) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default

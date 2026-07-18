"""
nlp/medical_parser.py

Turns raw extracted report text into structured parameter data:
    [{ "name": "Hemoglobin", "value": 10.2, "unit": "g/dL",
       "normal_range": "12.0 - 16.0", "status": "Low" }, ...]

Approach: for each known parameter (utils/normal_ranges.py) we build a
regex that looks for its aliases followed by a number, then classify the
value as Low / Normal / High (or a custom label like "Deficient") based on
the reference range.

This is a lightweight stand-in for a full spaCy NER pipeline. In a more
advanced version, this module could instead use a spaCy `EntityRuler`
or a fine-tuned biomedical NER model (e.g. scispaCy) to spot parameter
mentions, which would generalize better to messy real-world report layouts.
"""

import re
from utils.normal_ranges import PARAMETERS


def _build_pattern(aliases):
    alias_group = "|".join(aliases)
    # label ... optional colon/dash ... number (supports decimals)
    return re.compile(
        rf"(?:{alias_group})\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)",
        re.IGNORECASE,
    )


# Pre-compile patterns once at import time for speed
_COMPILED_PATTERNS = {
    name: _build_pattern(info["aliases"]) for name, info in PARAMETERS.items()
}


def _classify(value: float, info: dict) -> str:
    if value < info["low"]:
        return info["low_label"]
    if value > info["high"]:
        return info["high_label"]
    return "Normal"


def parse_parameters(text: str) -> list:
    """Scan `text` for every known parameter and return structured results.

    If a parameter appears multiple times, the first (usually most relevant)
    match is used.
    """
    found = []
    seen_names = set()

    for name, pattern in _COMPILED_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        if name in seen_names:
            continue

        try:
            # Use the LAST captured group, in case an alias regex contains
            # its own internal groups (e.g. inside a lookahead) — the
            # numeric value is always the final capture group by construction.
            value = float(match.groups()[-1])
        except (ValueError, IndexError, TypeError):
            continue

        info = PARAMETERS[name]
        status = _classify(value, info)

        found.append({
            "name": name,
            "value": value,
            "unit": info["unit"],
            "normal_range": f"{info['low']} - {info['high']}",
            "status": status,
        })
        seen_names.add(name)

    return found

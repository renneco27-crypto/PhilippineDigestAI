"""
utils/text_utils.py — Text compression and line classification utilities.
All re.compile() patterns are imported from utils/regex_utils.py.
No inline pattern definitions.
"""

import re
from difflib import get_close_matches

from models.constants import BOILERPLATE_PATTERNS
from models.legal_dictionary import CANONICAL_TERMS
from utils.regex_utils import (
    EMPHASIS_PATTERN,
    XXX_PATTERN,
    FOOTNOTE_REF_PATTERN,
    MULTI_SPACE_PATTERN,
    CITATION_LINE_PATTERN,
    GR_PATTERN,
    DATE_PATTERN,
)

# Pre-compile BOILERPLATE_PATTERNS once at import time
_BOILERPLATE_COMPILED: list[re.Pattern] = [
    re.compile(p) for p in BOILERPLATE_PATTERNS
]

# HardWords terms that should never appear in Section 2 (Legal Vocabulary).
# Two categories are blocked:
#   (a) Citation/reference shorthand: per se, supra, ibid, etc.
#   (b) Procedural meta-terms: terms that appear in the source text but are
#       generic procedural labels, statute names, or AI-hallucinated doctrine
#       rather than vocabulary terms actually defined by the case.
HARDWORDS_BLOCKLIST: set[str] = {
    # Citation / reference shorthand
    "per se", "a fortiori", "inter alia", "viz", "viz.",
    "supra", "infra", "ibid", "id", "et al", "et seq",
    "relator", "therein", "thereof", "whereby",
    # Procedural meta-terms — appear in source text but are NOT case vocabulary
    "ponente",            # author of the decision, not a legal doctrine
    "rollo",              # record on appeal folder label, not a doctrine
    "revised penal code", # statute name, not a term defined by the case
    "dispositive portion",# generic label for the fallo, not a doctrine term
    "a quo",              # not in HardWords — commonly hallucinated
    "rules of court",     # procedural rules codex, not a case-specific term
    "republic act",       # statute prefix, not a vocabulary term
    "article",            # statute subdivision label, not a doctrine term
    "so ordered",         # formulaic closing phrase, not a doctrine
    "docket fee",         # incidental MTC procedural note, not case doctrine
    "via certiorari",     # duplicate of certiorari + not the decided doctrine
    "slander by deed",    # always superseded by "serious slander by deed"
}


def filter_hard_words(terms: list[str]) -> list[str]:
    """Remove blocklisted and very short terms from a HardWords list."""
    return [
        t for t in terms
        if t.strip().lower() not in HARDWORDS_BLOCKLIST
        and len(t.strip()) > 3
    ]


def is_boilerplate_line(line: str) -> bool:
    """Return True if the line should be excluded from processing.

    Matches against BOILERPLATE_PATTERNS from models/constants.py
    and selected regex_utils patterns.
    """
    stripped = line.strip()
    for pattern in _BOILERPLATE_COMPILED:
        if pattern.search(stripped):
            return True
    return False


def is_citation_line(line: str) -> bool:
    """Return True if the line is a pure case citation footnote line.

    Used by p02_scan.py to skip citation lines during scanning.
    e.g. "1. Tanada v. Cuenco, G.R. No. L-10520, February 28, 1957"
    """
    return bool(CITATION_LINE_PATTERN.match(line))


def strip_layer_one(line: str) -> str:
    """Apply safe Layer 1 compressions to a single line.

    Layer 1 removes noise annotations that add no informational value:
      - "(Emphases supplied)" and variants
      - "[footnote_number]" inline references
      - Collapses multiple spaces into one
    The line's substantive text is preserved.
    """
    line = EMPHASIS_PATTERN.sub("", line)
    line = FOOTNOTE_REF_PATTERN.sub("", line)
    line = MULTI_SPACE_PATTERN.sub(" ", line)
    return line.strip()


def compress_chunk(lines: list[str]) -> str:
    """Two-layer compression. Returns a single compressed string.

    Layer 1 (per-line, safe):
      - Remove emphasis annotations
      - Remove inline footnote refs
      - Collapse multiple spaces

    Layer 2 (whole-chunk, aggressive):
      - Drop pure citation footnote lines entirely
      - Drop lines that are "x x x" separators only
      - Join remaining lines with newlines

    The result is a compact string ready for AI consumption.
    """
    # Layer 1: clean each line
    layer1: list[str] = []
    for line in lines:
        cleaned = strip_layer_one(line)
        if cleaned:  # drop lines that become empty after stripping
            layer1.append(cleaned)

    # Layer 2: filter whole lines
    layer2: list[str] = []
    for line in layer1:
        # Drop pure citation footnote lines
        if is_citation_line(line):
            continue
        # Drop lines that are solely "x x x" separators
        if XXX_PATTERN.fullmatch(line.strip()):
            continue
        layer2.append(line)

    return "\n".join(layer2)


def normalize_legal_terms(text: str) -> str:
    """Replace known misspellings of Spanish legal terms with canonical forms.
    Preserves case: Title Case, UPPERCASE, and lowercase inputs.
    """
    for wrong, correct in CANONICAL_TERMS.items():
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)

        def _replace(m: re.Match, correct: str = correct) -> str:
            matched = m.group(0)
            if matched.istitle():
                return correct.title()
            if matched.isupper():
                return correct.upper()
            return correct

        text = pattern.sub(_replace, text)
    return text


def fuzzy_correct_term(term: str) -> str:
    """Fuzzy-match a single term against canonical list (cutoff 0.85)."""
    canonical_list = list(CANONICAL_TERMS.values())
    matches = get_close_matches(
        term.lower(),
        [c.lower() for c in canonical_list],
        n=1, cutoff=0.85
    )
    if matches:
        idx = [c.lower() for c in canonical_list].index(matches[0])
        return canonical_list[idx]
    return term

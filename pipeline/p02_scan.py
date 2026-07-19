"""
pipeline/p02_scan.py — Phase 2: Keyword Scanning Engine.

Single-pass Aho-Corasick scan over case lines, deduplication, and
pre-extraction of verbatim text for doctrine/fallo/ruling hits.

No re.compile() calls here — all patterns imported from utils/regex_utils.py.
"""

import json
import sys

import ahocorasick

from config import (
    DEFAULT_MIN_GAP,
    INTERMEDIATE_HITS_PATH,
    INTERMEDIATE_LINES_PATH,
    VERBATIM_WINDOW,
)
from models.constants import KEYWORDS
from models.types import KeywordHit
from utils.regex_utils import CITATION_LINE_PATTERN

# Categories whose hits warrant pre-extraction of surrounding verbatim text
_VERBATIM_CATEGORIES: frozenset[str] = frozenset({"doctrine", "fallo", "ruling"})


# ── Public functions ──────────────────────────────────────────────────────────

def build_automaton(keywords: dict[str, str]) -> ahocorasick.Automaton:
    """Build an Aho-Corasick automaton from the KEYWORDS dict.

    Keys are stored as UPPERCASE for case-insensitive matching.
    Each automaton value is a tuple: (idx, original_keyword, category).
    """
    A = ahocorasick.Automaton()
    for idx, (keyword, category) in enumerate(keywords.items()):
        A.add_word(keyword.upper(), (idx, keyword, category))
    A.make_automaton()
    return A


def scan_lines(
    lines: list[str],
    automaton: ahocorasick.Automaton,
) -> list[KeywordHit]:
    """Single-pass scan. Returns raw (possibly duplicate) hits.

    Lines matching CITATION_LINE_PATTERN are skipped entirely.
    Returns KeywordHit objects in line-index order (unsorted within same line).
    """
    hits: list[KeywordHit] = []

    for line_idx, line in enumerate(lines):
        # Skip pure citation footnote lines
        if CITATION_LINE_PATTERN.match(line):
            continue

        upper_line = line.upper()
        seen_in_line: set[str] = set()

        for _end_idx, (_, keyword, category) in automaton.iter(upper_line):
            # Avoid duplicate keyword matches within the same line
            if keyword in seen_in_line:
                continue
            seen_in_line.add(keyword)

            hit: KeywordHit = {
                "line_idx": line_idx,
                "line_text": line,
                "keyword": keyword,
                "category": category,
                "local_verbatim": "",  # populated later by pre_extract_verbatim
            }
            hits.append(hit)

    return hits


def deduplicate_hits(
    hits: list[KeywordHit],
    min_gap: int = DEFAULT_MIN_GAP,
) -> list[KeywordHit]:
    """Remove hits within min_gap lines of each other for the SAME keyword.

    Algorithm:
      - Sort by line_idx.
      - Keep the first hit; discard a subsequent hit only if it shares
        the same keyword AND is within min_gap lines of that keyword's
        last kept occurrence.
    Returns a new list; input is not mutated.
    """
    if not hits:
        return []

    sorted_hits = sorted(hits, key=lambda h: h["line_idx"])
    kept: list[KeywordHit] = [sorted_hits[0]]
    last_idx_per_kw: dict[str, int] = {sorted_hits[0]["keyword"]: sorted_hits[0]["line_idx"]}

    for hit in sorted_hits[1:]:
        kw = hit["keyword"]
        last_idx = last_idx_per_kw.get(kw, -min_gap)
        if hit["line_idx"] - last_idx >= min_gap:
            kept.append(hit)
            last_idx_per_kw[kw] = hit["line_idx"]

    return kept


def pre_extract_verbatim(
    lines: list[str],
    hit: KeywordHit,
    window: int = VERBATIM_WINDOW,
) -> str:
    """For doctrine/fallo/ruling hits: grab surrounding lines as local verbatim.

    Returns an empty string for all other categories.
    The window is clamped to valid line indices.
    """
    if hit["category"] not in _VERBATIM_CATEGORIES:
        return ""

    idx = hit["line_idx"]
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    surrounding = lines[start:end]

    # Strip blank lines from edges, join with newline
    return "\n".join(line for line in surrounding if line.strip())


# ── I/O helpers (used by __main__ block and by run.py) ───────────────────────

def load_lines(path: str = INTERMEDIATE_LINES_PATH) -> list[str]:
    """Read the line-numbered file back into a plain list of strings.

    Each line in the file has the format "0000|text".
    Returns only the text portion, in order.
    """
    lines: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if "|" in raw:
                _num, _, text = raw.partition("|")
                lines.append(text)
            else:
                lines.append(raw)
    return lines


def save_hits(hits: list[KeywordHit], path: str = INTERMEDIATE_HITS_PATH) -> None:
    """Serialize hits list to JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(hits, fh, ensure_ascii=False, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Phase 2 — Keyword Scanning Engine")
    print("=" * 45)

    # Step 1: Load lines from intermediate file
    print(f"Loading lines from {INTERMEDIATE_LINES_PATH} …")
    lines = load_lines(INTERMEDIATE_LINES_PATH)
    print(f"  Loaded {len(lines)} lines.")

    # Step 2: Build automaton
    print(f"Building Aho-Corasick automaton ({len(KEYWORDS)} keywords) …")
    A = build_automaton(KEYWORDS)

    # Step 3: Scan
    print("Scanning …")
    raw_hits = scan_lines(lines, A)
    print(f"  Raw hits: {len(raw_hits)}")

    # Step 4: Deduplicate
    hits = deduplicate_hits(raw_hits)
    print(f"  Hits after dedup (min_gap={DEFAULT_MIN_GAP}): {len(hits)}")

    # Step 5: Pre-extract verbatim for doctrine/fallo/ruling hits
    for hit in hits:
        hit["local_verbatim"] = pre_extract_verbatim(lines, hit, window=VERBATIM_WINDOW)

    doctrine_count = sum(
        1 for h in hits if h["category"] in _VERBATIM_CATEGORIES
    )

    # Step 6: Save
    save_hits(hits)
    print(f"\nSaved {len(hits)} hits → {INTERMEDIATE_HITS_PATH}")
    print(f"Found {len(hits)} hits after dedup | Doctrine hits: {doctrine_count}")

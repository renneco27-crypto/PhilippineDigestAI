"""
pipeline/p05_stitch.py — Phase 6: Local Stitch & Verbatim Verification.

Merges all ChunkDataPackets into a single compiled_stream.txt:
  - sort_packets: sort by SourceLines start index
  - verify_verbatim: fuzzy-check VerbatimText against original source
  - deduplicate_names / deduplicate_hard_words: global dedup across packets
  - build_compiled_stream: assemble the final stream string

No AI calls. No re.compile() calls (uses SOURCE_LINES_START_PATTERN from regex_utils).
SequenceMatcher is stdlib difflib — no new dependencies.
"""

import json
import os
import re
from difflib import SequenceMatcher

from config import (
    INTERMEDIATE_CONTEXT_PATH,
    INTERMEDIATE_LINES_PATH,
    INTERMEDIATE_PACKETS_PATH,
    INTERMEDIATE_STREAM_PATH,
    VERBATIM_THRESHOLD,
)
from models.constants import PIPELINE_METADATA_PATTERNS
from models.types import ChunkDataPacket, GlobalContext
from utils.regex_utils import SOURCE_LINES_START_PATTERN
from models.legal_dictionary import CANONICAL_TERMS
from utils.text_utils import filter_hard_words, normalize_legal_terms

# Window size (in lines) used for the sliding verbatim check
_VERBATIM_SLIDE_WINDOW: int = 8

# Pre-compile pipeline metadata patterns once at import time
_METADATA_COMPILED: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE) for p in PIPELINE_METADATA_PATTERNS
]


# ── Public functions ──────────────────────────────────────────────────────────

def sort_packets(packets: list[ChunkDataPacket]) -> list[ChunkDataPacket]:
    """Sort packets by the integer start of packet["SourceLines"] (ascending).

    e.g. "120–195" → sort key 120.
    Packets with unparseable SourceLines sort to the end (key = 999999).
    Returns a NEW list; the input list is not mutated.
    """
    def _sort_key(packet: ChunkDataPacket) -> int:
        m = SOURCE_LINES_START_PATTERN.search(packet.get("SourceLines", ""))
        return int(m.group(1)) if m else 999_999

    return sorted(packets, key=_sort_key)


def verify_verbatim(
    candidate: str,
    original_lines: list[str],
    threshold: float = VERBATIM_THRESHOLD,
) -> str:
    """Fuzzy-check verbatim text against the original source lines.

    - If candidate is empty or "NOT_PRESENT": return candidate unchanged.
    - Slides an 8-line window over original_lines and computes
      SequenceMatcher ratio against the first 200 chars of candidate.
    - If best_ratio >= threshold: candidate passes, return it.
    - If best_ratio < threshold: print a warning and return the best-matching
      window text from source as a corrected replacement.
    - All SequenceMatcher exceptions are caught; candidate is returned on error.

    Uses VERBATIM_THRESHOLD from config.py.
    """
    if not candidate or candidate.strip() in ("", "NOT_PRESENT"):
        return candidate

    candidate_sample = candidate[:200].lower()
    best_ratio: float = 0.0
    best_match: str = candidate

    try:
        total = len(original_lines)
        for i in range(total):
            window_lines = original_lines[i : i + _VERBATIM_SLIDE_WINDOW]
            window_text = " ".join(window_lines)[:200].lower()
            try:
                ratio = SequenceMatcher(None, candidate_sample, window_text).ratio()
            except Exception:
                continue
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = " ".join(window_lines)

        if best_ratio >= threshold:
            return candidate  # AI text is accurate enough
        else:
            print(
                f"  [verbatim warn] ratio={best_ratio:.2f} < {threshold:.2f}\n"
                f"    candidate : {candidate[:80]!r}\n"
                f"    source    : {best_match[:80]!r}"
            )
            return best_match

    except Exception as exc:
        print(f"  [verbatim error] SequenceMatcher failed: {exc}")
        return candidate


def deduplicate_hard_words(packets: list[ChunkDataPacket]) -> list[str]:
    """Collect unique HardWords entries across all packets.

    Skips "NOT_PRESENT" and empty strings.
    Strips AI-generated descriptions before comparing, so the same term
    from different chunks collapses to one entry regardless of description
    wording. Preserves first-seen insertion order.
    Returns list[str] (term names only, no descriptions).
    """
    seen: set[str] = set()
    result: list[str] = []
    for packet in packets:
        entry = packet.get("HardWords", "").strip()
        if not entry or entry == "NOT_PRESENT":
            continue
        # Each packet may contain multiple terms separated by newlines or semicolons
        for term in entry.replace(";", "\n").split("\n"):
            term = term.strip()
            if not term:
                continue
            # Strip description, extract just the term name
            name = _term_name(term)
            if not name:
                continue
            # Normalize for comparison
            key = normalize_legal_terms(name.rstrip(".,;:").lower())
            if key and key not in seen:
                seen.add(key)
                result.append(name)  # clean term name, no description
    # Semantic dedup pass (name-only, threshold 0.70)
    result = _semantic_deduplicate(result)

    return filter_hard_words(result)


def deduplicate_names(packets: list[ChunkDataPacket]) -> set[str]:
    """Collect unique party names across all packets.

    Splits each packet["Names"] on comma.
    Strips whitespace and skips strings shorter than 4 characters.
    Skips "NOT_PRESENT".
    Returns set[str].
    """
    names: set[str] = set()
    for packet in packets:
        raw = packet.get("Names", "")
        if not raw or raw.strip() == "NOT_PRESENT":
            continue
        for name in raw.split(","):
            name = name.strip()
            if len(name) >= 4:
                names.add(name)
    return names


def verify_hard_words_against_source(
    terms: list[str],
    lines: list[str],
) -> list[str]:
    """Cross-reference each AI-generated HardWords term against the original
    source lines. Discard any term not found verbatim in the case text.
    This is the ground-truth check that prevents hallucinated vocabulary.

    HardWords entries may include a description after ' — ' or ' - ' or '�';
    only the term name (before the separator) is checked against source.
    """
    source_text = " ".join(lines).lower()
    result: list[str] = []
    for term in terms:
        # Extract term name — discard any description after separator
        name = term.split(" — ")[0].split(" – ")[0].split(" - ")[0].split("�")[0].strip()
        if name.lower() in source_text:
            result.append(term)
    return result


def _semantic_deduplicate(terms: list[str], threshold: float = 0.75) -> list[str]:
    """Remove semantically duplicate terms by name comparison.

    Compares each term against every kept term using SequenceMatcher
    on the normalized lowercase name. If ratio >= threshold the
    shorter term is kept (preferring canonical legal forms).

    This catches near-duplicates like 'indeterminate sentence'
    vs 'Indeterminate Sentence Law' while keeping legally distinct
    terms like 'reclusion perpetua' vs 'reclusion temporal'.
    """
    if len(terms) < 2:
        return terms

    # Build normalized versions for comparison
    normed: list[str] = []
    for t in terms:
        n = normalize_legal_terms(t.lower()).rstrip(".,;:")
        normed.append(n)

    kept: list[bool] = [True] * len(terms)
    canonical_keys = {k.lower() for k in CANONICAL_TERMS.values()}

    for i in range(len(terms)):
        if not kept[i]:
            continue
        for j in range(i + 1, len(terms)):
            if not kept[j]:
                continue
            ratio = SequenceMatcher(None, normed[i], normed[j]).ratio()
            if ratio < threshold:
                continue
            # Decide which to drop: prefer canonical, then shorter
            i_canon = normed[i] in canonical_keys
            j_canon = normed[j] in canonical_keys
            if i_canon and not j_canon:
                kept[j] = False
            elif j_canon and not i_canon:
                kept[i] = False
            elif len(normed[j]) < len(normed[i]):
                kept[i] = False
            else:
                kept[j] = False
            break  # term i resolved against first close match

    return [terms[i] for i in range(len(terms)) if kept[i]]


def _term_name(raw: str) -> str:
    """Extract the term name from a raw HardWords entry (strip description)."""
    return raw.split(" — ")[0].split(" – ")[0].split(" - ")[0].split("�")[0].strip()


def build_compiled_stream(
    packets: list[ChunkDataPacket],
    original_lines: list[str],
    global_context: GlobalContext,
) -> str:
    """Merge all packets into the final compiled stream string.

    Section order and exact labels are fixed — the Reduce AI prompt
    references them by name. Do not alter labels or whitespace.

    Steps:
      1. sort_packets
      2. deduplicate_names, deduplicate_hard_words
      3. verify_hard_words_against_source (ground-truth check)
      4. verify_verbatim per packet
      5. Assemble stream with exact format from spec
    """
    sorted_pkts = sort_packets(packets)
    all_names = deduplicate_names(sorted_pkts)
    all_hard_words = deduplicate_hard_words(sorted_pkts)

    # Remove hallucinated terms not in the original source text
    all_hard_words = verify_hard_words_against_source(all_hard_words, original_lines)

    lines_out: list[str] = []

    # ── Header ──────────────────────────────────────────────────────────────
    lines_out.append("=== COMPILED CASE STREAM ===")
    lines_out.append(f"GR Number: {global_context['gr_number']}")
    lines_out.append(f"Petitioner: {global_context['petitioner']}")
    lines_out.append(f"Respondent: {global_context['respondent']}")
    lines_out.append(f"Promulgation Date: {global_context['promulgation_date']}")
    lines_out.append(f"Division: {global_context['division']}")
    lines_out.append(f"Ponente: {global_context['ponente']}")
    lines_out.append(f"Bar Subject: {global_context['bar_subject']}")
    lines_out.append(f"Source URL: {global_context['source_url']}")

    # ── Deterministic fallo verbatim ────────────────────────────────────────
    lines_out.append(f"SC_FALLO_VERBATIM: {global_context['sc_fallo']}")

    # ── Party names ──────────────────────────────────────────────────────────
    lines_out.append(f"All Parties: {', '.join(sorted(all_names))}")

    # ── Locked HardWords list (term names only, stripped of descriptions) ──
    locked_terms = [_term_name(t) for t in all_hard_words]
    lines_out.append("")
    lines_out.append(f"HARDWORDS_LOCKED: {', '.join(locked_terms)}")

    # ── Chunk stream ─────────────────────────────────────────────────────────
    lines_out.append("")
    lines_out.append("=== CHUNK STREAM (chronological order) ===")
    lines_out.append("")

    for n, packet in enumerate(sorted_pkts, start=1):
        verified_verbatim = verify_verbatim(
            packet.get("VerbatimText", ""),
            original_lines,
            threshold=VERBATIM_THRESHOLD,
        )

        lines_out.append(
            f"[CHUNK {n} | Lines: {packet.get('SourceLines', 'N/A')}"
            f" | Trigger: {packet.get('Keyword', 'N/A')}]"
        )
        lines_out.append(f"  RootDispute:      {packet.get('RootDispute', 'NOT_PRESENT')}")
        lines_out.append(f"  Dates:            {packet.get('Dates', 'NOT_PRESENT')}")
        lines_out.append(f"  ProceduralAction: {packet.get('ProceduralAction', 'NOT_PRESENT')}")
        lines_out.append(f"  OperativeFacts:   {packet.get('OperativeFacts', 'NOT_PRESENT')}")
        lines_out.append(f"  VerbatimText:     {verified_verbatim}")
        lines_out.append(f"  Commentary:       {packet.get('Commentary', 'NOT_PRESENT')}")
        lines_out.append("")  # blank line between chunks

    result = "\n".join(lines_out)
    return strip_pipeline_metadata(result)


def strip_pipeline_metadata(stream: str) -> str:
    """Remove all pipeline metadata lines and inline labels from the
    compiled stream before passing to the reduce stage.

    Catches:
      - Lines starting with 'This chunk occurs when'
      - Lines starting with 'This establishes'
      - Inline labels like (Chunk 1 & 2), (SC_FALLO_VERBATIM – Chunk 8),
        (Excerpt from CA decision – Chunk 1)

    Uses PIPELINE_METADATA_PATTERNS from models/constants.py.
    """
    cleaned_lines = []
    for line in stream.splitlines():
        stripped = line.strip()
        if any(p.search(stripped) for p in _METADATA_COMPILED):
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines)


# Keep old name as alias so any existing callers don't break
strip_context_headers = strip_pipeline_metadata


def verify_usage_examples(
    digest: str,
    source_lines: list[str],
    threshold: float = 0.75,
) -> tuple[list[dict], str]:
    """Cross-reference usage examples in Section 2 against the source lines.

    Extracts every line starting with 'Example:' or 'Usage Example:' from
    the digest, then scores each against the source using SequenceMatcher.
    For flagged examples below the threshold, replaces the example text
    with the best-matching verbatim source line (capped at 300 chars).

    Returns (flagged_list, corrected_digest):
        flagged: list of dicts with keys:
            {"example": str, "confidence": float, "status": "FABRICATED"|"LOW_CONFIDENCE"}
        corrected_digest: the digest with flagged examples replaced.

    Scores:
        >= threshold  → passes (not flagged)
        0.4–threshold → LOW_CONFIDENCE
        < 0.4         → FABRICATED
    """
    example_pattern = re.compile(
        r'(?:\*\*)?(?:Usage\s+)?[Ee]xample:\s*(?:\*\*)?\s*["]?(.+?)["]?\s*(?:\*\*)?\s*$'
    )

    if not source_lines:
        return [], digest

    flagged: list[dict] = []
    corrected_lines: list[str] = []

    for line in digest.splitlines():
        m = example_pattern.search(line)
        if not m:
            corrected_lines.append(line)
            continue

        example_text = m.group(1).strip()
        # Strip any remaining markdown bold markers
        example_text = example_text.replace("**", "").strip()
        if not example_text or len(example_text) < 10:
            corrected_lines.append(line)
            continue

        candidate = example_text[:200].lower()
        best_ratio = 0.0
        best_window = ""

        # Slide an 8-line window across source to find best match.
        # Compare against each individual line (for exact matches) and
        # the concatenated window (for multi-line matches).
        for i in range(len(source_lines)):
            window_lines = source_lines[i: i + _VERBATIM_SLIDE_WINDOW]
            window = " ".join(window_lines)[:200].lower()
            try:
                ratio = SequenceMatcher(None, candidate, window).ratio()
            except Exception:
                continue
            # Also check each individual line — catches exact matches
            # that get diluted by concatenation
            for sl in window_lines:
                try:
                    sl_score = SequenceMatcher(None, candidate, sl[:200].lower()).ratio()
                    if sl_score > ratio:
                        ratio = sl_score
                except Exception:
                    continue
            if ratio > best_ratio:
                best_ratio = ratio
                best_window = " ".join(window_lines)
            if best_ratio >= threshold:
                break  # early exit — passes

        if best_ratio >= threshold:
            corrected_lines.append(line)
            continue

        # Flagged — auto-correct with best-match source (capped at 300 chars)
        status = "FABRICATED" if best_ratio < 0.4 else "LOW_CONFIDENCE"
        flagged.append({
            "example": example_text,
            "confidence": round(best_ratio, 3),
            "status": status,
        })

        # Reconstruct line keeping everything before group(1) +
        # a space + verbatim + rest of line after full match
        before_example = line[:m.start(1)]
        after_match = line[m.end():]
        verbatim = best_window[:300]
        corrected_lines.append(f"{before_example.rstrip()} {verbatim}{after_match}")

    return flagged, "\n".join(corrected_lines)


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_packets(path: str) -> list[ChunkDataPacket]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_lines(path: str) -> list[str]:
    """Read line-numbered intermediate file into plain list."""
    result: list[str] = []
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.rstrip("\n")
            if "|" in raw:
                _num, _, text = raw.partition("|")
                result.append(text)
            else:
                result.append(raw)
    return result


def _load_global_context(path: str) -> GlobalContext:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_stream(stream: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(stream)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Phase 6 — Local Stitch & Verbatim Verification")
    print("=" * 50)

    # Step 1: Load inputs
    print(f"Loading packets from {INTERMEDIATE_PACKETS_PATH} …")
    packets = _load_packets(INTERMEDIATE_PACKETS_PATH)

    print(f"Loading original lines from {INTERMEDIATE_LINES_PATH} …")
    original_lines = _load_lines(INTERMEDIATE_LINES_PATH)

    print(f"Loading global context from {INTERMEDIATE_CONTEXT_PATH} …")
    global_context = _load_global_context(INTERMEDIATE_CONTEXT_PATH)

    # Step 2: Build compiled stream
    print(f"Stitching {len(packets)} packets …")
    compiled_stream = build_compiled_stream(packets, original_lines, global_context)

    # Step 3: Normalize Spanish legal spellings
    compiled_stream = normalize_legal_terms(compiled_stream)

    # Step 4: Save
    _save_stream(compiled_stream, INTERMEDIATE_STREAM_PATH)

    char_count = len(compiled_stream)
    est_tokens = int(char_count / 4)  # rough estimate: ~4 chars per token

    print(f"\nSaved compiled stream → {INTERMEDIATE_STREAM_PATH}")
    print(f"  Characters : {char_count:,}")
    print(f"  Est. tokens: ~{est_tokens:,}")
    print(f"Stitch complete. {len(packets)} packets merged.")

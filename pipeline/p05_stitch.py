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
from difflib import SequenceMatcher

from config import (
    INTERMEDIATE_CONTEXT_PATH,
    INTERMEDIATE_LINES_PATH,
    INTERMEDIATE_PACKETS_PATH,
    INTERMEDIATE_STREAM_PATH,
    VERBATIM_THRESHOLD,
)
from models.types import ChunkDataPacket, GlobalContext
from utils.regex_utils import SOURCE_LINES_START_PATTERN
from utils.text_utils import filter_hard_words, normalize_legal_terms

# Window size (in lines) used for the sliding verbatim check
_VERBATIM_SLIDE_WINDOW: int = 8


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

    return "\n".join(lines_out)


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

"""
pipeline/p03_chunk.py — Phase 3: Chunk Assembly & Compression.

Converts each KeywordHit into a ChunkPayload:
  - Slices a window of lines around the hit
  - Compresses via utils.text_utils.compress_chunk (NOT redefined here)
  - Builds a context_header prefix string
  - Records source_lines range with en-dash (U+2013)

No re.compile() calls. compress_chunk is imported, never redefined.
"""

import json
import sys

from config import (
    DEFAULT_WINDOW,
    INTERMEDIATE_CONTEXT_PATH,
    INTERMEDIATE_HITS_PATH,
    INTERMEDIATE_LINES_PATH,
    INTERMEDIATE_PAYLOADS_PATH,
)
from models.types import ChunkPayload, GlobalContext, KeywordHit
from utils.text_utils import compress_chunk  # imported, not redefined

# Context header format (must not exceed 200 characters)
_CONTEXT_HEADER_TEMPLATE = (
    "[CONTEXT] GR: {gr_number} | PETITIONER={petitioner_short}"
    " | RESPONDENT={respondent_short}"
    " | Focus: {bar_subject} | Trigger: {keyword} ({category})"
)

# En-dash character for source_lines format per spec
_EN_DASH = "\u2013"


# ── Public functions ──────────────────────────────────────────────────────────

def build_context_header(hit: KeywordHit, global_context: GlobalContext) -> str:
    """Build the one-line [CONTEXT] prefix string injected into every chunk.

    Petitioner and respondent are truncated to 60 characters.
    The full string must not exceed 200 characters per spec.
    Returns the formatted string.
    """
    header = _CONTEXT_HEADER_TEMPLATE.format(
        gr_number=global_context["gr_number"],
        petitioner_short=global_context["petitioner_short"][:60],
        respondent_short=global_context["respondent_short"][:60],
        bar_subject=global_context["bar_subject"],
        keyword=hit["keyword"],
        category=hit["category"],
    )
    # Hard-truncate to 200 chars as a safety net (should not trigger normally)
    return header[:200]


def build_chunk_payload(
    lines: list[str],
    hit: KeywordHit,
    global_context: GlobalContext,
    window: int = DEFAULT_WINDOW,
) -> ChunkPayload:
    """Build a single ChunkPayload from a KeywordHit.

    Slices lines[start:end] around hit["line_idx"] (clamped to valid range),
    compresses the slice, builds the context_header, and assembles the payload.

    source_lines format: "120\u2013195" (en-dash, not hyphen).
    chunk_index equals hit["line_idx"].
    All ChunkPayload fields are populated.
    """
    idx = hit["line_idx"]
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)

    chunk_lines = lines[start:end]
    compressed = compress_chunk(chunk_lines)
    context_header = build_context_header(hit, global_context)
    source_lines = f"{start}{_EN_DASH}{end - 1}"

    payload: ChunkPayload = {
        "chunk_index": idx,
        "keyword": hit["keyword"],
        "category": hit["category"],
        "source_lines": source_lines,
        "local_verbatim": hit["local_verbatim"],
        "context_header": context_header,
        "chunk_text": compressed,
    }
    return payload


def build_all_payloads(
    lines: list[str],
    hits: list[KeywordHit],
    global_context: GlobalContext,
    window: int = DEFAULT_WINDOW,
) -> list[ChunkPayload]:
    """Build all ChunkPayloads. Wraps build_chunk_payload in a loop.

    Returns list[ChunkPayload] in the same order as the hits input.
    """
    return [
        build_chunk_payload(lines, hit, global_context, window)
        for hit in hits
    ]


# ── I/O helpers ───────────────────────────────────────────────────────────────

def _load_lines(path: str) -> list[str]:
    """Read line-numbered file into plain list."""
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


def _load_hits(path: str) -> list[KeywordHit]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _load_global_context(path: str) -> GlobalContext:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _save_payloads(payloads: list[ChunkPayload], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payloads, fh, ensure_ascii=False, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Phase 3 — Chunk Assembly & Compression")
    print("=" * 45)

    # Step 1: Load inputs
    print(f"Loading lines from {INTERMEDIATE_LINES_PATH} …")
    lines = _load_lines(INTERMEDIATE_LINES_PATH)

    print(f"Loading hits from {INTERMEDIATE_HITS_PATH} …")
    hits = _load_hits(INTERMEDIATE_HITS_PATH)

    print(f"Loading global context from {INTERMEDIATE_CONTEXT_PATH} …")
    global_context = _load_global_context(INTERMEDIATE_CONTEXT_PATH)

    # Step 2: Build payloads
    print(f"Building {len(hits)} payloads (window={DEFAULT_WINDOW}) …")
    payloads = build_all_payloads(lines, hits, global_context, window=DEFAULT_WINDOW)

    # Step 3: Validate context_header lengths
    long_headers = [p for p in payloads if len(p["context_header"]) > 200]
    if long_headers:
        print(f"  WARNING: {len(long_headers)} context_headers exceed 200 chars (truncated).")

    # Step 4: Estimate token count
    est_tokens = sum(len(p["chunk_text"].split()) * 1.3 for p in payloads)

    # Step 5: Save
    _save_payloads(payloads, INTERMEDIATE_PAYLOADS_PATH)

    print(f"\nSaved {len(payloads)} payloads → {INTERMEDIATE_PAYLOADS_PATH}")
    print(f"Built {len(payloads)} payloads | Est. total tokens: {int(est_tokens)}")

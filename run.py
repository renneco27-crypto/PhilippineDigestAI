"""
run.py
Single-command orchestrator for the Philippine Case Digest AI pipeline.

Usage:
  python run.py "https://lawphil.net/..." --subject "Political & International Law"
  python run.py input/case.pdf --pdf --subject "Civil Law"

Rules:
  - Imports pipeline functions directly (no subprocess calls).
  - The ProviderSwarm is built ONCE here and passed to stages that need it.
  - All intermediate and output paths come from config.py.
  - Each stage result is stored in PipelineState before the next stage runs.
  - Invalid --subject exits with a helpful message before running anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

# ---------------------------------------------------------------------------
# Config and models — imported before anything else so path constants resolve.
# ---------------------------------------------------------------------------
import config
from config import (
    INTERMEDIATE_CONTEXT_PATH,
    INTERMEDIATE_HITS_PATH,
    INTERMEDIATE_PAYLOADS_PATH,
    INTERMEDIATE_PACKETS_PATH,
    INTERMEDIATE_STREAM_PATH,
    OUTPUT_DIGEST_PATH,
)
from models.types import PipelineState, GlobalContext
from models.constants import BAR_SUBJECTS, KEYWORDS

# ---------------------------------------------------------------------------
# Pipeline stage imports — modules only, not subprocess.
# ---------------------------------------------------------------------------
from pipeline.p00_fetch import fetch_case_from_url, ingest_pdf, save_lines, load_lines
from pipeline.p02_scan import build_automaton, scan_lines, deduplicate_hits, pre_extract_verbatim
from pipeline.p03_chunk import build_all_payloads
from pipeline.p04_map import process_all_chunks
from pipeline.p05_stitch import build_compiled_stream
from pipeline.p06_reduce import run_reduce
from swarm import build_default_swarm, ProviderSwarm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEP_WIDTH = 55

def _stage_banner(n: int | str, name: str) -> None:
    print("=" * _SEP_WIDTH)
    print(f">>> STAGE {n}: {name}")
    print("=" * _SEP_WIDTH)


def _save_json(obj: object, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def _load_json(path: str) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run.py",
        description="Philippine Case Digest AI — end-to-end pipeline runner.",
        epilog=(
            "Examples:\n"
            '  python run.py "https://lawphil.net/..." '
            '--subject "Political & International Law"\n'
            '  python run.py input/case.pdf --pdf --subject "Civil Law"'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        help="URL to a Lawphil/SC E-Library case, or path to a local PDF file.",
    )
    parser.add_argument(
        "--subject",
        default="Political & International Law",
        metavar="SUBJECT",
        help=(
            "Bar subject to focus the digest on. "
            f"One of: {', '.join(repr(s) for s in BAR_SUBJECTS)}. "
            'Default: "Political & International Law".'
        ),
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Treat <source> as a local PDF file path instead of a URL.",
    )
    return parser


# ---------------------------------------------------------------------------
# Main pipeline runner
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    # Validate bar subject before touching the network or disk.
    if args.subject not in BAR_SUBJECTS:
        print(
            f"[run.py] ERROR: Unknown bar subject: {args.subject!r}\n"
            f"  Valid values:\n"
            + "\n".join(f"    - {s}" for s in BAR_SUBJECTS),
            file=sys.stderr,
        )
        sys.exit(1)

    # Ensure output directories exist.
    os.makedirs("intermediate", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    # Build the swarm ONCE — passed to stages that need it.
    swarm: ProviderSwarm = build_default_swarm()

    # Initialise PipelineState with known-at-start fields.
    state: PipelineState = PipelineState(
        url=args.source if not args.pdf else "",
        bar_subject=args.subject,
        lines=[],
        global_context=GlobalContext(
            petitioner="", respondent="", petitioner_short="",
            respondent_short="", complainant="", ca_penalty="", gr_number="",
            promulgation_date="", ponente="", division="",
            sc_fallo="",
            source_url=args.source if not args.pdf else "",
            bar_subject=args.subject,
        ),
        hits=[],
        payloads=[],
        packets=[],
        compiled_stream="",
        digest="",
    )

    # -----------------------------------------------------------------------
    # STAGE 0 — Fetch / ingest
    # -----------------------------------------------------------------------
    _stage_banner(0, "Fetch / Ingest")
    try:
        if args.pdf:
            lines, global_context = ingest_pdf(args.source)
        else:
            lines, global_context = fetch_case_from_url(args.source)

        # Stamp the user-chosen bar subject onto global_context.
        global_context["bar_subject"] = args.subject

        state["lines"] = lines
        state["global_context"] = global_context

        save_lines(lines)
        _save_json(dict(global_context), INTERMEDIATE_CONTEXT_PATH)

        print(
            f"Fetched {len(lines)} lines | "
            f"GR: {global_context['gr_number']} | "
            f"Petitioner: {global_context['petitioner']}"
        )
    except Exception as exc:
        print(f"[STAGE 0 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # STAGE 2 — Keyword scan
    # -----------------------------------------------------------------------
    _stage_banner(2, "Keyword Scan")
    try:
        automaton = build_automaton(KEYWORDS)
        raw_hits = scan_lines(state["lines"], automaton)
        hits = deduplicate_hits(raw_hits)

        # Pre-extract verbatim for doctrine/fallo/ruling hits.
        for hit in hits:
            hit["local_verbatim"] = pre_extract_verbatim(state["lines"], hit)

        state["hits"] = hits
        _save_json([dict(h) for h in hits], INTERMEDIATE_HITS_PATH)

        doctrine_count = sum(1 for h in hits if h["category"] in ("doctrine", "fallo", "ruling"))
        print(f"Found {len(hits)} hits after dedup | Doctrine hits: {doctrine_count}")
    except Exception as exc:
        print(f"[STAGE 2 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # STAGE 3 — Chunk assembly
    # -----------------------------------------------------------------------
    _stage_banner(3, "Chunk Assembly & Compression")
    try:
        payloads = build_all_payloads(
            state["lines"],
            state["hits"],
            state["global_context"],
        )
        state["payloads"] = payloads
        _save_json([dict(p) for p in payloads], INTERMEDIATE_PAYLOADS_PATH)

        est_tokens = int(sum(len(p["chunk_text"].split()) * 1.3 for p in payloads))
        print(f"Built {len(payloads)} payloads | Est. total tokens: {est_tokens}")
    except Exception as exc:
        print(f"[STAGE 3 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # STAGE 4 — Map (parallel AI calls)
    # -----------------------------------------------------------------------
    _stage_banner(4, "Map Stage (Parallel AI Calls)")
    try:
        packets = process_all_chunks(state["payloads"], swarm)
        state["packets"] = packets
        _save_json([dict(p) for p in packets], INTERMEDIATE_PACKETS_PATH)

        success = sum(
            1 for p in packets
            if p["RootDispute"] not in ("PARSE_ERROR", "SWARM_FAILURE", "MISSING_RESULT")
        )
        print(f"Map complete: {success}/{len(packets)} chunks processed successfully")
    except Exception as exc:
        print(f"[STAGE 4 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # STAGE 5 — Stitch
    # -----------------------------------------------------------------------
    _stage_banner(5, "Local Stitch & Verbatim Verification")
    try:
        compiled_stream = build_compiled_stream(
            state["packets"],
            state["lines"],
            state["global_context"],
        )
        state["compiled_stream"] = compiled_stream

        with open(INTERMEDIATE_STREAM_PATH, "w", encoding="utf-8") as fh:
            fh.write(compiled_stream)

        char_count = len(compiled_stream)
        print(
            f"Stitch complete. {len(state['packets'])} packets merged. "
            f"Stream: {char_count} chars (~{char_count // 4} tokens)"
        )
    except Exception as exc:
        print(f"[STAGE 5 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # STAGE 6 — Reduce (single AI call → Master Digest)
    # -----------------------------------------------------------------------
    _stage_banner(6, "Reduce Stage (Master Digest)")
    try:
        # Raise per-provider max_tokens for the longer reduce output.
        for provider in swarm._providers:
            provider.max_tokens = config.REDUCE_MAX_TOKENS

        digest = run_reduce(
            state["compiled_stream"],
            state["global_context"],
            swarm,
        )
        state["digest"] = digest

        with open(OUTPUT_DIGEST_PATH, "w", encoding="utf-8") as fh:
            fh.write(digest)

        print(f"Digest saved to {OUTPUT_DIGEST_PATH} ({len(digest)} characters)")
    except Exception as exc:
        print(f"[STAGE 6 ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Final summary
    # -----------------------------------------------------------------------
    gc = state["global_context"]
    print()
    print("Done.")
    print(f"  GR Number:   {gc['gr_number']}")
    print(f"  Bar Subject: {gc['bar_subject']}")
    print(f"  Output:      {OUTPUT_DIGEST_PATH}")


if __name__ == "__main__":
    main()

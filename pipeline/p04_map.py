"""
pipeline/p04_map.py
Stage 4 — Map: dispatch all ChunkPayloads to the AI swarm in parallel.
Each payload becomes one ChunkDataPacket.

Key rules (from Cross-Phase Rules §8):
  - VerbatimText is ALWAYS overwritten from payload["local_verbatim"].
    It is never trusted from the AI response.
  - process_all_chunks() returns packets in the same order as the input payloads.
  - The swarm singleton is passed in; never constructed here.
"""

from __future__ import annotations

import json
import sys
from typing import Optional

from models.types import ChunkPayload, ChunkDataPacket, SwarmTask
from models.constants import CHUNK_DATA_FIELDS
from utils.regex_utils import CHUNK_DATA_PATTERN, FIELD_PATTERN_MAP
from swarm import ProviderSwarm
from config import (
    INTERMEDIATE_PAYLOADS_PATH,
    INTERMEDIATE_PACKETS_PATH,
)

# ---------------------------------------------------------------------------
# Map system prompt — fixed module-level constant. Never built dynamically.
# VerbatimText is intentionally absent: it is injected from local_verbatim.
# ---------------------------------------------------------------------------
MAP_SYSTEM_PROMPT: str = (
    "You are a legal data extraction node. Extract only what is present in the chunk.\n"
    "RESPOND ONLY WITH THE <ChunkData> BLOCK. No preamble. No explanation outside tags.\n"
    "\n"
    "Output format:\n"
    "<ChunkData>\n"
    "Names: [party names found, or NOT_PRESENT]\n"
    "Dates: [exact dates found, or NOT_PRESENT]\n"
    "RootDispute: [origin of conflict in 1 sentence, or NOT_PRESENT]\n"
    "ProceduralAction: [court movements: MTC/RTC/CA/SC, or NOT_PRESENT]\n"
    "OperativeFacts: [facts that trigger the legal issue, or NOT_PRESENT]\n"
    "HardWords: [term — plain definition, or NOT_PRESENT]\n"
    "Commentary: [2 sentences: \"This chunk occurs when [X]...\" "
    "\"This establishes [Y]...\"]\n"
    "</ChunkData>"
)


# ---------------------------------------------------------------------------
# build_user_content
# ---------------------------------------------------------------------------

def build_user_content(payload: ChunkPayload) -> str:
    """
    Build the user message string from a ChunkPayload.
    Format: context_header + separator + chunk_text.
    """
    return payload["context_header"] + "\n\n---\n" + payload["chunk_text"]


# ---------------------------------------------------------------------------
# parse_chunk_data_response
# ---------------------------------------------------------------------------

def _make_error_packet(payload: ChunkPayload, reason: str = "PARSE_ERROR") -> ChunkDataPacket:
    """Return a ChunkDataPacket with all extracted fields set to reason."""
    return ChunkDataPacket(
        Names=reason,
        Dates=reason,
        RootDispute=reason,
        ProceduralAction=reason,
        OperativeFacts=reason,
        HardWords=reason,
        Commentary=reason,
        VerbatimText=payload["local_verbatim"],   # always from source
        SourceLines=payload["source_lines"],
        Keyword=payload["keyword"],
        Category=payload["category"],
    )


def parse_chunk_data_response(raw: str, payload: ChunkPayload) -> ChunkDataPacket:
    """
    Parse <ChunkData>…</ChunkData> XML from the AI response.
    After extraction, VerbatimText is unconditionally overwritten with
    payload["local_verbatim"] — the source-extracted version.
    Returns a complete ChunkDataPacket.
    """
    if not raw:
        return _make_error_packet(payload)

    block_match = CHUNK_DATA_PATTERN.search(raw)
    if not block_match:
        print(f"[p04_map] WARNING: No <ChunkData> block found for keyword={payload['keyword']!r}")
        return _make_error_packet(payload)

    block_text = block_match.group(1)

    # Extract the seven AI-generated fields.
    ai_fields = ("Names", "Dates", "RootDispute", "ProceduralAction",
                 "OperativeFacts", "HardWords", "Commentary")
    extracted: dict[str, str] = {}
    for field_name in ai_fields:
        pattern = FIELD_PATTERN_MAP.get(field_name)
        if pattern is None:
            extracted[field_name] = "PARSE_ERROR"
            continue
        m = pattern.search(block_text)
        extracted[field_name] = m.group(1).strip() if m else "NOT_PRESENT"

    # Build the packet. VerbatimText is source-overridden — never from AI.
    packet = ChunkDataPacket(
        Names=extracted.get("Names", "NOT_PRESENT"),
        Dates=extracted.get("Dates", "NOT_PRESENT"),
        RootDispute=extracted.get("RootDispute", "NOT_PRESENT"),
        ProceduralAction=extracted.get("ProceduralAction", "NOT_PRESENT"),
        OperativeFacts=extracted.get("OperativeFacts", "NOT_PRESENT"),
        HardWords=extracted.get("HardWords", "NOT_PRESENT"),
        Commentary=extracted.get("Commentary", "NOT_PRESENT"),
        VerbatimText=payload["local_verbatim"],   # source override — non-negotiable
        SourceLines=payload["source_lines"],
        Keyword=payload["keyword"],
        Category=payload["category"],
    )
    return packet


# ---------------------------------------------------------------------------
# process_all_chunks
# ---------------------------------------------------------------------------

def process_all_chunks(
    payloads: list[ChunkPayload],
    swarm: ProviderSwarm,
) -> list[ChunkDataPacket]:
    """
    Map stage: dispatch all payloads in parallel via the swarm.
    Returns a list of ChunkDataPacket in the same order as the input payloads.
    Any None (failed) result is replaced with an error packet.
    """
    # Pre-size results list so order is preserved regardless of thread timing.
    results: list[Optional[ChunkDataPacket]] = [None] * len(payloads)

    # Build SwarmTask list.
    tasks: list[SwarmTask] = [
        SwarmTask(index=i, content=build_user_content(payload))
        for i, payload in enumerate(payloads)
    ]

    # Callback executed by each worker thread as it finishes.
    def _callback(index: int, raw_response: Optional[str]) -> None:
        payload = payloads[index]
        if raw_response is None:
            results[index] = _make_error_packet(payload, reason="SWARM_FAILURE")
        else:
            results[index] = parse_chunk_data_response(raw_response, payload)

    swarm.dispatch_parallel(tasks, MAP_SYSTEM_PROMPT, _callback)

    # Safety pass: fill any slot that a thread somehow skipped.
    for i, packet in enumerate(results):
        if packet is None:
            results[i] = _make_error_packet(payloads[i], reason="MISSING_RESULT")

    return results  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# __main__ — Stage 4 standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from swarm import build_default_swarm

    print("Loading payloads…")
    with open(INTERMEDIATE_PAYLOADS_PATH, encoding="utf-8") as fh:
        payloads_raw = json.load(fh)
    payloads: list[ChunkPayload] = [ChunkPayload(**p) for p in payloads_raw]

    print(f"  {len(payloads)} payloads loaded.")
    swarm = build_default_swarm()

    packets = process_all_chunks(payloads, swarm)

    # Serialise to JSON.
    with open(INTERMEDIATE_PACKETS_PATH, "w", encoding="utf-8") as fh:
        json.dump([dict(pkt) for pkt in packets], fh, ensure_ascii=False, indent=2)

    success = sum(1 for p in packets if p["RootDispute"] not in ("PARSE_ERROR", "SWARM_FAILURE", "MISSING_RESULT"))
    print(f"Map complete: {success}/{len(packets)} chunks processed successfully")
    print(f"Packets saved to {INTERMEDIATE_PACKETS_PATH}")

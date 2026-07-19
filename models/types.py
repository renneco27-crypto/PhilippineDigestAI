# models/types.py
# CANONICAL TYPE DEFINITIONS — Do not alter field names.
# All data structures passed between pipeline stages are defined here.
# Every pipeline file imports its types from this module only.

from typing import TypedDict, Optional, Callable


class GlobalContext(TypedDict):
    petitioner: str            # Full petitioner name from case caption
    respondent: str            # Full respondent name from case caption
    petitioner_short: str      # First part of petitioner name (before comma)
    respondent_short: str      # First part of respondent name (before comma)
    gr_number: str             # e.g. "G.R. No. 208566"
    promulgation_date: str     # e.g. "November 19, 2013"
    ponente: str               # e.g. "Perlas-Bernabe"
    division: str              # e.g. "FIRST DIVISION", "EN BANC"
    sc_fallo: str              # Deterministically extracted SC fallo text
    source_url: str            # URL (empty string if PDF source)
    bar_subject: str           # e.g. "Political & International Law"
    complainant: str           # Private complainant name extracted from Facts body
                               # (distinct from respondent in caption; empty if not a
                               #  criminal case or if none found)


class KeywordHit(TypedDict):
    line_idx: int              # Zero-based index into the lines list
    line_text: str             # Raw text of the triggering line
    keyword: str               # The matched keyword string
    category: str              # Category from KEYWORDS dict
    local_verbatim: str        # Pre-extracted surrounding text (empty if non-doctrine)


class ChunkPayload(TypedDict):
    chunk_index: int           # Same as hit's line_idx — used for sort order
    keyword: str
    category: str
    source_lines: str          # e.g. "120–195" (en-dash U+2013)
    local_verbatim: str        # Pre-extracted verbatim (empty if not doctrine/fallo/ruling)
    context_header: str        # Pre-built one-line context string (≤200 chars)
    chunk_text: str            # Compressed chunk text ready for AI


class ChunkDataPacket(TypedDict):
    Names: str
    Dates: str
    RootDispute: str
    ProceduralAction: str
    OperativeFacts: str
    HardWords: str
    Commentary: str
    VerbatimText: str          # Always overwritten with local_verbatim post-parse
    SourceLines: str
    Keyword: str
    Category: str


class SwarmTask(TypedDict):
    index: int                 # Position in the payloads list (used to sort results back)
    content: str               # Full user message string for the AI call


class PipelineState(TypedDict):
    """Single state dict passed through run.py to track the entire run."""
    url: str                             # Source URL (empty if PDF run)
    bar_subject: str                     # One of BAR_SUBJECTS
    lines: list[str]                     # Clean line list from p00_fetch
    global_context: GlobalContext        # Extracted case metadata
    hits: list[KeywordHit]              # Deduplicated keyword hits from p02_scan
    payloads: list[ChunkPayload]        # Assembled chunk payloads from p03_chunk
    packets: list[ChunkDataPacket]      # AI-returned + locally overridden packets from p04_map
    compiled_stream: str                 # Stitched stream text from p05_stitch
    digest: str                          # Final Master Digest text from p06_reduce

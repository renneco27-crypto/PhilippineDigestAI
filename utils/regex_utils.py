# utils/regex_utils.py
# ALL pre-compiled regex patterns for the entire project.
# Rules:
#   1. This file contains ONLY module-level re.Pattern constants.
#   2. No function definitions in this file.
#   3. No re.compile() call may exist anywhere else in the project.
#   4. All pipeline files that need a pattern import it from here by name.

import re
from models.constants import BOILERPLATE_PATTERNS, CHUNK_DATA_FIELDS

# ---------------------------------------------------------------------------
# Case Caption Extraction Patterns
# ---------------------------------------------------------------------------

# Matches "G.R. No. 208566" or "G.R. No. 208566-67" variants
GR_PATTERN: re.Pattern = re.compile(
    r'G\.R\.?\s*No\.?\s*[\d][\d\-]+',
    re.IGNORECASE
)

# Matches "November 19, 2013" style full promulgation dates
DATE_PATTERN: re.Pattern = re.compile(
    r'(?:January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+\d{1,2},\s+\d{4}',
    re.IGNORECASE
)

# Matches "LASTNAME, J." or "LASTNAME, C.J." style ponente lines
# Captures the name portion before the comma
PONENTE_PATTERN: re.Pattern = re.compile(
    r'([A-Z][A-Z\s\-]+),\s*(?:C\.)?J\.?\b'
)

# Matches the "Petitioner vs. Respondent" block in case caption
# Captures group(1)=petitioner side, group(2)=respondent side
VS_PATTERN: re.Pattern = re.compile(
    r'(.+?)\s*,\s*petitioners?\s*,?\s*(?:vs\.?|versus)\s*(.+?),\s*respondents?',
    re.DOTALL | re.IGNORECASE
)

# Matches "EN BANC" or division name in case caption (FIRST/SECOND/THIRD/SPECIAL FIRST DIVISION)
DIVISION_PATTERN: re.Pattern = re.compile(
    r'\b(EN BANC|FIRST DIVISION|SECOND DIVISION|THIRD DIVISION|SPECIAL FIRST DIVISION)\b',
    re.IGNORECASE
)

# Fallo extractor — finds the dispositive portion between opener and "SO ORDERED"
# Last match in the document is always the SC's own fallo.
FALLO_PATTERN: re.Pattern = re.compile(
    r'(ACCORDINGLY|WHEREFORE|IN VIEW OF THE FOREGOING|FOR THESE REASONS|PREMISES CONSIDERED)'
    r'(.+?)'
    r'SO ORDERED',
    re.DOTALL | re.IGNORECASE
)

# Matches GR number from URL path segment e.g. "gr_208566" or "gr-208566"
URL_GR_PATTERN: re.Pattern = re.compile(
    r'gr[_\-](\d+)',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# Text Compression Patterns (used in utils/text_utils.py)
# ---------------------------------------------------------------------------

# Matches "(Emphases supplied)", "(Emphasis supplied)", "(Underscoring supplied)", etc.
EMPHASIS_PATTERN: re.Pattern = re.compile(
    r'\(Emphases?\s+(?:and\s+underscoring\s+)?supplied\)',
    re.IGNORECASE
)

# Matches "x x x" and "x x x x" ellipsis separators used in SC decisions
XXX_PATTERN: re.Pattern = re.compile(
    r'\bx\s+x\s+x(?:\s+x)?\b',
    re.IGNORECASE
)

# Matches inline footnote reference markers like "[1]" "[23]" "[100]"
FOOTNOTE_REF_PATTERN: re.Pattern = re.compile(
    r'\[\d+\]'
)

# Matches 2 or more consecutive whitespace characters (spaces, tabs)
MULTI_SPACE_PATTERN: re.Pattern = re.compile(
    r'\s{2,}'
)

# ---------------------------------------------------------------------------
# Citation Line Detection Pattern (Layer 2 compression — skip entire line)
# Matches lines that are pure case citation footnotes, e.g.:
#   "Abakada Guro v. Purisima, 400 Phil. 669 (2008)."
#   "Republic v. CA, G.R. No. 12345, March 1, 2000, 300 SCRA 123."
# ---------------------------------------------------------------------------
CITATION_LINE_PATTERN: re.Pattern = re.compile(
    r'^[A-Z][a-z].{5,}(?:Phil\.|SCRA|SCR\.|O\.G\.|G\.R\.).*\d{4}',
    re.IGNORECASE
)

# ---------------------------------------------------------------------------
# ChunkData XML Parsing Patterns
# ---------------------------------------------------------------------------

# Matches the full <ChunkData>...</ChunkData> block from AI response
CHUNK_DATA_PATTERN: re.Pattern = re.compile(
    r'<ChunkData>(.*?)</ChunkData>',
    re.DOTALL
)

# Per-field extractor: captures value after "FieldName: " up to next field or end of block
# Used to build FIELD_PATTERN_MAP below
def _make_field_pattern(field_name: str) -> re.Pattern:
    return re.compile(
        rf'{re.escape(field_name)}:\s*(.*?)(?=\n[A-Za-z]+:|$)',
        re.DOTALL
    )

# Maps each ChunkData field name → its compiled extractor pattern
# Used by p04_map.py: parse_chunk_data_response()
FIELD_PATTERN_MAP: dict[str, re.Pattern] = {
    field: _make_field_pattern(field)
    for field in CHUNK_DATA_FIELDS
    if field not in ("VerbatimText", "SourceLines", "Keyword", "Category")
    # VerbatimText, SourceLines, Keyword, Category are injected locally — never parsed from AI
}

# ---------------------------------------------------------------------------
# Boilerplate Line Detection
# Compiled from BOILERPLATE_PATTERNS list in models/constants.py
# Used by utils/text_utils.py: is_boilerplate_line()
# ---------------------------------------------------------------------------
_COMPILED_BOILERPLATE: list[re.Pattern] = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in BOILERPLATE_PATTERNS
]
# Exported as a single tuple for fast iteration
COMPILED_BOILERPLATE_PATTERNS: tuple[re.Pattern, ...] = tuple(_COMPILED_BOILERPLATE)

# ---------------------------------------------------------------------------
# Source Lines Sort Key Pattern
# Extracts the leading integer from "120–195" for sort_packets() in p05_stitch.py
# ---------------------------------------------------------------------------
SOURCE_LINES_START_PATTERN: re.Pattern = re.compile(r'^(\d+)')

# ---------------------------------------------------------------------------
# Issue Extraction Patterns (used by p06_reduce.py: extract_stated_issues)
# Patterns match Philippine SC decision issue-framing language.
# Each captures exactly one sentence (stops at ". The" / ". This" etc.)
# ---------------------------------------------------------------------------
ISSUE_PATTERNS: tuple[re.Pattern, ...] = (
    # "The issue in this case is whether X is Y"
    re.compile(
        r'(?:the\s+)?(?:issue|question)\s+(?:in\s+this\s+case\s+)?'
        r'(?:for\s+(?:resolution|consideration|determination)\s+)?'
        r'(?:is|are|raised|presented|assigned)\s*[:;]?\s*'
        r'(.+?)'
        r'(?:\.\s+(?:The|We|This|Petitioner|Respondent|Thus|However|In|It)|$)',
        re.IGNORECASE | re.DOTALL
    ),
    # "Petitioner assigns the following errors: ..."
    re.compile(
        r'(?:assign(?:ed|s)?\s+(?:the\s+)?(?:following\s+)?error[s]?\s*[:;]?\s*)'
        r'(.+?)'
        r'(?:\.\s+(?:The|We|This|Petitioner|Respondent|Thus|However|In|It)|$)',
        re.IGNORECASE | re.DOTALL
    ),
    # "WHETHER OR NOT X IS Y"
    re.compile(
        r'(?:whether\s+or\s+not\s+)'
        r'(.+?)'
        r'(?:\?|\.\s+(?:The|We|This))',
        re.IGNORECASE | re.DOTALL
    ),
    # "The sole/controlling question for resolution is ..."
    re.compile(
        r'(?:the\s+)?(?:sole|main|central|principal|pivotal|controlling)\s+'
        r'(?:issue|question)\s+'
        r'(?:is|involves|concerns|relates\s+to|presented\s+is)\s+'
        r'(.+?)'
        r'(?:\.\s+(?:The|We|This|Thus|However|In|It)|$)',
        re.IGNORECASE | re.DOTALL
    ),
)

# pipeline/p00_fetch.py
# Stage 0: Web Fetch OR PDF Ingest → clean line list + GlobalContext
#
# Web-fetch path: full implementation (Lawphil / SC E-Library URLs)
# PDF ingest path: stub — raises NotImplementedError (implemented in Phase 1 extension)
#
# Canonical function signatures — do not alter:
#   fetch_case_from_url(url)         -> tuple[list[str], GlobalContext]
#   ingest_pdf(pdf_path)             -> tuple[list[str], GlobalContext]
#   extract_global_context_from_html(soup, url) -> GlobalContext
#   extract_global_context_from_lines(lines)    -> GlobalContext
#   is_boilerplate_line(line)        -> bool
#   save_lines(lines, path)          -> None
#   load_lines(path)                 -> list[str]

import re
import sys
import json

import requests
from bs4 import BeautifulSoup

from config import (
    FETCH_HEADERS,
    FETCH_TIMEOUT,
    INTERMEDIATE_LINES_PATH,
    INTERMEDIATE_CONTEXT_PATH,
)
from models.types import GlobalContext
from utils.text_utils import is_boilerplate_line
from utils.regex_utils import (
    GR_PATTERN,
    DATE_PATTERN,
    PONENTE_PATTERN,
    VS_PATTERN,
    DIVISION_PATTERN,
    URL_GR_PATTERN,
    FALLO_PATTERN,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_case_from_url(url: str) -> tuple[list[str], GlobalContext]:
    """
    Fetch a Lawphil or SC E-Library case page by URL.
    Strips HTML, removes boilerplate lines, and extracts global case metadata.
    Returns (lines, global_context).
    """
    resp = requests.get(url, headers=FETCH_HEADERS, timeout=FETCH_TIMEOUT)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    global_context = extract_global_context_from_html(soup, url)

    # Remove non-content tags before text extraction
    for tag in soup(["script", "style", "nav", "header", "footer", "a"]):
        tag.decompose()

    raw_text = soup.get_text(separator="\n")

    lines: list[str] = []
    for raw_line in raw_text.split("\n"):
        clean = raw_line.strip()
        if not clean:
            continue
        if is_boilerplate_line(clean):
            continue
        lines.append(clean)

    return lines, global_context


def ingest_pdf(pdf_path: str) -> tuple[list[str], GlobalContext]:
    """
    Parse a local Philippine SC decision PDF into clean lines + GlobalContext.
    STUB — not implemented in Phase 1. Will be implemented in a later session.
    """
    raise NotImplementedError(
        "PDF ingestion is not yet implemented. "
        "Use fetch_case_from_url() with a Lawphil or SC E-Library URL instead."
    )


def extract_global_context_from_html(soup: BeautifulSoup, url: str) -> GlobalContext:
    """
    Extract case metadata from parsed HTML structure.
    Uses only pre-compiled patterns from utils/regex_utils.py.
    Falls back to "Unknown" for any field not found.
    """
    context: GlobalContext = {
        "petitioner": "Unknown",
        "respondent": "Unknown",
        "petitioner_short": "Unknown",
        "respondent_short": "Unknown",
        "gr_number": "Unknown",
        "promulgation_date": "Unknown",
        "ponente": "Unknown",
        "division": "Unknown",
        "sc_fallo": "",
        "source_url": url,
        "bar_subject": "",  # Set by caller (run.py or __main__ block)
        "complainant": "",  # Extracted below from body text; empty if not found
        "ca_penalty": "",   # Extracted below from body text; empty if not found
    }

    # GR number from URL path (most reliable — Lawphil URLs contain the GR)
    url_gr_match = URL_GR_PATTERN.search(url)
    if url_gr_match:
        context["gr_number"] = f"G.R. No. {url_gr_match.group(1)}"

    # Scan only the first 3,000 chars of page text for metadata
    page_text = soup.get_text()[:3000]

    gr_match = GR_PATTERN.search(page_text)
    if gr_match:
        context["gr_number"] = gr_match.group(0).strip()

    date_match = DATE_PATTERN.search(page_text)
    if date_match:
        context["promulgation_date"] = date_match.group(0).strip()

    ponente_match = PONENTE_PATTERN.search(page_text)
    if ponente_match:
        context["ponente"] = ponente_match.group(1).strip().title()

    division_match = DIVISION_PATTERN.search(page_text)
    if division_match:
        context["division"] = division_match.group(0).strip()

    vs_match = VS_PATTERN.search(page_text)
    if vs_match:
        context["petitioner"] = vs_match.group(1).strip()
        context["respondent"] = vs_match.group(2).strip()[:200].strip()

    # Short party names (first part before comma)
    context["petitioner_short"] = context["petitioner"].split(",")[0].strip()
    context["respondent_short"] = context["respondent"].split(",")[0].strip()

    # SC fallo — last FALLO_PATTERN match in the full document
    full_text = soup.get_text()
    all_fallos = list(FALLO_PATTERN.finditer(full_text))
    if all_fallos:
        context["sc_fallo"] = all_fallos[-1].group(0).strip()

    # Private complainant — look for "private complainant" or "complainant"
    # phrase in the body text, then capture the nearest proper name.
    # Pattern: "complainant[,]? [Name]" or "[Name][,]? the complainant"
    complainant_pattern = re.compile(
        r"(?:private\s+)?complainant[,\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
        r"|([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})[,\s]+(?:the\s+)?(?:private\s+)?complainant",
        re.IGNORECASE,
    )
    complainant_match = complainant_pattern.search(full_text)
    if complainant_match:
        # group(1) = "complainant NAME" form; group(2) = "NAME complainant" form
        name = (complainant_match.group(1) or complainant_match.group(2) or "").strip()
        context["complainant"] = name

    # CA penalty — look for CA-imposed penalty phrase in the body text
    ca_penalty_pattern = re.compile(
        r"(?:Court of Appeals|CA)\s+(?:imposed|affirmed|modified).*?"
        r"(?:penalty|sentence).{0,80}?"
        r"(?:\d+\s+years?[^.]*|arresto mayor|prision correccional"
        r"|prision mayor|reclusion temporal|reclusion perpetua)[^.]*\.",
        re.IGNORECASE | re.DOTALL,
    )
    ca_match = ca_penalty_pattern.search(full_text)
    if ca_match:
        context["ca_penalty"] = ca_match.group(0).strip()

    return context


def extract_global_context_from_lines(lines: list[str]) -> GlobalContext:
    """
    Extract case metadata from plain text lines (PDF ingestion path).
    Uses only pre-compiled patterns from utils/regex_utils.py.
    Scans the first 50 lines where the case caption always appears.
    """
    context: GlobalContext = {
        "petitioner": "Unknown",
        "respondent": "Unknown",
        "petitioner_short": "Unknown",
        "respondent_short": "Unknown",
        "gr_number": "Unknown",
        "promulgation_date": "Unknown",
        "ponente": "Unknown",
        "division": "Unknown",
        "sc_fallo": "",
        "source_url": "",
        "bar_subject": "",
        "complainant": "",  # Extracted below from body text; empty if not found
        "ca_penalty": "",   # Extracted below from body text; empty if not found
    }

    header_text = "\n".join(lines[:50])

    gr_match = GR_PATTERN.search(header_text)
    if gr_match:
        context["gr_number"] = gr_match.group(0).strip()

    date_match = DATE_PATTERN.search(header_text)
    if date_match:
        context["promulgation_date"] = date_match.group(0).strip()

    ponente_match = PONENTE_PATTERN.search(header_text)
    if ponente_match:
        context["ponente"] = ponente_match.group(1).strip().title()

    division_match = DIVISION_PATTERN.search(header_text)
    if division_match:
        context["division"] = division_match.group(0).strip()

    vs_match = VS_PATTERN.search(header_text)
    if vs_match:
        context["petitioner"] = vs_match.group(1).strip()[-200:].strip()
        context["respondent"] = vs_match.group(2).strip()[:200].strip()

    # Fallback: look for "v." line in first 50 lines
    if context["petitioner"] == "Unknown":
        for i, line in enumerate(lines[:50]):
            if " v. " in line or " vs. " in line.lower():
                if i > 0:
                    context["petitioner"] = lines[i - 1].strip()
                if i < len(lines) - 1:
                    context["respondent"] = lines[i + 1].strip()
                break

    # Short party names (first part before comma)
    context["petitioner_short"] = context["petitioner"].split(",")[0].strip()
    context["respondent_short"] = context["respondent"].split(",")[0].strip()

    # SC fallo from full text
    full_text = "\n".join(lines)
    all_fallos = list(FALLO_PATTERN.finditer(full_text))
    if all_fallos:
        context["sc_fallo"] = all_fallos[-1].group(0).strip()

    # Private complainant — same pattern as the HTML path
    complainant_pattern = re.compile(
        r"(?:private\s+)?complainant[,\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
        r"|([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})[,\s]+(?:the\s+)?(?:private\s+)?complainant",
        re.IGNORECASE,
    )
    complainant_match = complainant_pattern.search(full_text)
    if complainant_match:
        name = (complainant_match.group(1) or complainant_match.group(2) or "").strip()
        context["complainant"] = name

    # CA penalty — same pattern as the HTML path
    ca_penalty_pattern = re.compile(
        r"(?:Court of Appeals|CA)\s+(?:imposed|affirmed|modified).*?"
        r"(?:penalty|sentence).{0,80}?"
        r"(?:\d+\s+years?[^.]*|arresto mayor|prision correccional"
        r"|prision mayor|reclusion temporal|reclusion perpetua)[^.]*\.",
        re.IGNORECASE | re.DOTALL,
    )
    ca_match = ca_penalty_pattern.search(full_text)
    if ca_match:
        context["ca_penalty"] = ca_match.group(0).strip()

    return context


def save_lines(lines: list[str], path: str = INTERMEDIATE_LINES_PATH) -> None:
    """
    Write lines to disk in the canonical line-numbered format: '0000|text\\n'.
    Always uses INTERMEDIATE_LINES_PATH unless overridden.
    """
    with open(path, "w", encoding="utf-8") as f:
        for i, line in enumerate(lines):
            f.write(f"{i:04d}|{line}\n")


def load_lines(path: str = INTERMEDIATE_LINES_PATH) -> list[str]:
    """
    Read the canonical line-numbered file back into a plain list[str].
    Strips the '0000|' prefix — returns text only, no line numbers.
    """
    lines: list[str] = []
    with open(path, encoding="utf-8") as f:
        for row in f:
            parts = row.rstrip("\n").split("|", 1)
            if len(parts) == 2:
                lines.append(parts[1])
    return lines


# ---------------------------------------------------------------------------
# __main__ — test block
# Usage: python pipeline/p00_fetch.py "https://lawphil.net/..."
# Optional second arg: bar subject string
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import os

    if len(sys.argv) < 2:
        print("Usage: python pipeline/p00_fetch.py <URL> [bar_subject]")
        sys.exit(1)

    url = sys.argv[1]
    bar_subject = sys.argv[2] if len(sys.argv) > 2 else "Political & International Law"

    print(f"Fetching: {url}")
    lines, global_context = fetch_case_from_url(url)

    # Set bar_subject from CLI arg
    global_context["bar_subject"] = bar_subject

    # Ensure intermediate dir exists
    os.makedirs("intermediate", exist_ok=True)
    os.makedirs("output", exist_ok=True)

    save_lines(lines)

    with open(INTERMEDIATE_CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(global_context, f, indent=2, ensure_ascii=False)

    print(
        f"Fetched {len(lines)} lines | "
        f"GR: {global_context['gr_number']} | "
        f"Petitioner: {global_context['petitioner'][:60]}"
    )
    print(f"Saved → {INTERMEDIATE_LINES_PATH}")
    print(f"Saved → {INTERMEDIATE_CONTEXT_PATH}")

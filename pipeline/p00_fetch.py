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
from models.constants import LAW_ALIASES
from utils.text_utils import is_boilerplate_line
from utils.regex_utils import (
    GR_PATTERN,
    DATE_PATTERN,
    PONENTE_PATTERN,
    VS_PATTERN,
    DIVISION_PATTERN,
    URL_GR_PATTERN,
    FALLO_PATTERN,
    COMPOUND_ROLE_PATTERN,
    APPOSITIVE_PATTERN,
    PEOPLE_PATTERN,
    CORP_COMMA_PATTERN,
    NOISE_PATTERN,
    ROLE_SUFFIX_PATTERN,
    ET_AL_PATTERN,
    CONSOLIDATED_GR_PATTERN,
    PER_CURIAM_PATTERN,
    RULING_VERB_PATTERN,
    PARTIAL_QUALIFIER_PATTERN,
    PROVISION_LAW_PATTERN,
    STATUTE_PATTERN,
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

    # Use the last (most specific) GR match in the header zone.
    # Lawphil pages put the GR number in the <title> tag AND in the case header;
    # we want the header occurrence because the case date lives right after it
    # on the same line (e.g. "G.R. No. 119190 January 16, 1997").
    gr_matches = list(GR_PATTERN.finditer(page_text))
    if gr_matches:
        # Prefer a GR match that has a date within 150 chars (the header line).
        # Fall back to the first match if none has a co-located date.
        chosen_gr = gr_matches[0]
        for gm in gr_matches:
            window = page_text[gm.start(): gm.start() + 150]
            if DATE_PATTERN.search(window):
                chosen_gr = gm
                break
        context["gr_number"] = chosen_gr.group(0).strip()

        # Date: search only within 150 chars of the chosen GR match to avoid
        # the Lawphil nav bar "Today is [current date]" false positive.
        date_window = page_text[chosen_gr.start(): chosen_gr.start() + 150]
        date_match = DATE_PATTERN.search(date_window)
        if date_match:
            context["promulgation_date"] = date_match.group(0).strip()

    ponente_match = PONENTE_PATTERN.search(page_text)
    if ponente_match:
        # group(1) includes optional JR./SR. suffix; strip trailing comma artifact
        context["ponente"] = ponente_match.group(1).strip().rstrip(",").strip().title()

    division_match = DIVISION_PATTERN.search(page_text)
    if division_match:
        context["division"] = division_match.group(0).strip()

    vs_match = VS_PATTERN.search(page_text)
    if vs_match:
        # group(1) may contain nav-bar garbage before the actual name;
        # the real petitioner name is always the LAST non-empty line.
        raw_pet_lines = [l.strip() for l in vs_match.group(1).strip().split("\n") if l.strip()]
        context["petitioner"] = raw_pet_lines[-1] if raw_pet_lines else vs_match.group(1).strip()
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

    # Enrich with extractors (Modules 1-6)
    rough_lines = [l.strip() for l in full_text.split("\n") if l.strip()]
    context.update(extract_role_inversion(rough_lines, context))
    context.update(extract_parties(rough_lines))
    context.update(extract_consolidated_grs(rough_lines))
    context.update(extract_per_curiam(rough_lines))
    context.update(extract_ruling_nuance(rough_lines))
    context.update(extract_provisions(full_text))

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

    # Use the last (most specific) GR match, preferring one with a co-located date
    gr_matches = list(GR_PATTERN.finditer(header_text))
    if gr_matches:
        chosen_gr = gr_matches[0]
        for gm in gr_matches:
            window = header_text[gm.start(): gm.start() + 150]
            if DATE_PATTERN.search(window):
                chosen_gr = gm
                break
        context["gr_number"] = chosen_gr.group(0).strip()
        date_window = header_text[chosen_gr.start(): chosen_gr.start() + 150]
        date_match = DATE_PATTERN.search(date_window)
        if date_match:
            context["promulgation_date"] = date_match.group(0).strip()

    ponente_match = PONENTE_PATTERN.search(header_text)
    if ponente_match:
        context["ponente"] = ponente_match.group(1).strip().rstrip(",").strip().title()

    division_match = DIVISION_PATTERN.search(header_text)
    if division_match:
        context["division"] = division_match.group(0).strip()

    vs_match = VS_PATTERN.search(header_text)
    if vs_match:
        # group(1) may contain nav-bar garbage before the actual name;
        # the real petitioner name is always the LAST non-empty line.
        raw_pet_lines = [l.strip() for l in vs_match.group(1).strip().split("\n") if l.strip()]
        context["petitioner"] = raw_pet_lines[-1] if raw_pet_lines else vs_match.group(1).strip()
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

    # Enrich with extractors (Modules 1-6)
    context.update(extract_role_inversion(lines, context))
    context.update(extract_parties(lines))
    context.update(extract_consolidated_grs(lines))
    context.update(extract_per_curiam(lines))
    context.update(extract_ruling_nuance(lines))
    context.update(extract_provisions(full_text))

    return context


# ---------------------------------------------------------------------------
# Party split helper (Module 2)
# ---------------------------------------------------------------------------

def _split_parties(side: str) -> list[str]:
    """Split a party-side string into individual names.

    Protects 'Company, Inc.' style patterns before comma-splitting.
    Strips noise markers and role suffixes.
    """
    if not side:
        return []
    # Protect "Company, Inc." style patterns
    protected = CORP_COMMA_PATTERN.sub(lambda m: m.group(0).replace(",", "\u200b"), side)
    # Strip noise suffixes
    stripped = NOISE_PATTERN.sub("", protected)
    # Split by comma
    parts = [p.strip() for p in stripped.split(",") if p.strip()]
    # Restore protected commas
    parts = [p.replace("\u200b", ",") for p in parts]
    # Strip role suffixes
    parts = [ROLE_SUFFIX_PATTERN.sub("", p).strip() for p in parts]
    return [p for p in parts if len(p) >= 3]


# ---------------------------------------------------------------------------
# Helper: canonical law name from citation text
# ---------------------------------------------------------------------------

def _canonical_law(cite: str) -> str:
    """Extract and canonicalize the law name from a citation string."""
    cite_upper = cite.upper()
    # Check aliases (shortcuts like "FC", "RPC")
    for alias in sorted(LAW_ALIASES.keys(), key=len, reverse=True):
        if alias in cite_upper:
            return LAW_ALIASES[alias]
    # Check canonical values directly (e.g. "FAMILY CODE", "CIVIL CODE")
    for canonical in sorted(set(LAW_ALIASES.values()), key=len, reverse=True):
        if canonical in cite_upper:
            return canonical
    return "Unknown"


# ---------------------------------------------------------------------------
# Module 1 — Role inversion
# ---------------------------------------------------------------------------

def extract_role_inversion(lines: list[str], context: GlobalContext) -> dict:
    """
    Determine trial-court roles of the parties.

    Criminal shortcut: if PEOPLE_PATTERN matches the respondent side,
    the petitioner is the accused.
    Otherwise checks for compound roles (accused-appellant) and
    appositive phrases (petitioner, who was the defendant below).
    """
    result: dict = {
        "petitioner_trial_role": "Unknown",
        "respondent_trial_role": "Unknown",
    }
    if not lines:
        return result

    full_text = "\n".join(lines)
    petitioner = (context.get("petitioner") or "").lower()
    respondent = (context.get("respondent") or "").lower()

    # Criminal shortcut: People v. Accused
    if PEOPLE_PATTERN.search(respondent):
        result["petitioner_trial_role"] = "accused"
        result["respondent_trial_role"] = "state"
        return result

    # Compound role in petitioner name
    compound_m = COMPOUND_ROLE_PATTERN.search(petitioner)
    if compound_m:
        text = compound_m.group(0).lower()
        if "defendant" in text:
            result["petitioner_trial_role"] = "defendant"
        elif "accused" in text:
            result["petitioner_trial_role"] = "accused"
        elif "plaintiff" in text:
            result["petitioner_trial_role"] = "plaintiff"

    # Appositive phrase in full text
    app_m = APPOSITIVE_PATTERN.search(full_text)
    if app_m:
        ref_name = app_m.group(1).lower()
        trial_role = app_m.group(2).lower()
        if ref_name == "petitioner":
            result["petitioner_trial_role"] = trial_role
        elif ref_name == "respondent":
            result["respondent_trial_role"] = trial_role

    return result


# ---------------------------------------------------------------------------
# Module 2 — Multiple parties
# ---------------------------------------------------------------------------

def extract_parties(lines: list[str]) -> dict:
    """
    Extract full arrays of party names and detect 'et al.' in the caption.
    """
    result: dict = {"petitioners": [], "respondents": [], "has_et_al": False}
    if not lines:
        return result

    header_text = "\n".join(lines[:50])
    vs_m = VS_PATTERN.search(header_text)
    if not vs_m:
        return result

    petitioner_side = vs_m.group(1).strip()
    respondent_side = vs_m.group(2).strip()[:200].strip()

    result["has_et_al"] = bool(ET_AL_PATTERN.search(header_text))
    result["petitioners"] = _split_parties(petitioner_side)
    result["respondents"] = _split_parties(respondent_side)

    return result


# ---------------------------------------------------------------------------
# Module 3 — Consolidated GR numbers
# ---------------------------------------------------------------------------

def extract_consolidated_grs(lines: list[str]) -> dict:
    """
    Find all GR numbers in the header and detect consolidated cases.
    """
    result: dict = {"gr_numbers": [], "is_consolidated": False}
    if not lines:
        return result

    header_text = "\n".join(lines[:100])

    cons_m = CONSOLIDATED_GR_PATTERN.search(header_text)
    if cons_m:
        matched_text = cons_m.group(0)
        # Extract all digit sequences from the consolidated GR string
        digit_matches = re.findall(r'\b(\d+(?:-\d+)?)\b', matched_text)
        result["gr_numbers"] = ["G.R. No. " + d for d in digit_matches]
        result["is_consolidated"] = len(digit_matches) > 1
        return result

    # Fallback: single GR
    gr_m = GR_PATTERN.search(header_text)
    if gr_m:
        result["gr_numbers"] = [gr_m.group(0).strip()]
        result["is_consolidated"] = False

    return result


# ---------------------------------------------------------------------------
# Module 4 — Per Curiam
# ---------------------------------------------------------------------------

def extract_per_curiam(lines: list[str]) -> dict:
    """Detect whether the decision is per curiam from the header zone."""
    result: dict = {"is_per_curiam": False}
    if not lines:
        return result
    header_text = "\n".join(lines[:50])
    result["is_per_curiam"] = bool(PER_CURIAM_PATTERN.search(header_text))
    return result


# ---------------------------------------------------------------------------
# Module 5 — Ruling nuance
# ---------------------------------------------------------------------------

def extract_ruling_nuance(lines: list[str]) -> dict:
    """
    Extract ruling verbs from the dispositive and detect partial affirmance.

    Restricted to the last 15% of lines to avoid the CA ruling quotation trap.
    """
    result: dict = {
        "ruling_keywords": [],
        "ruling_is_partial": False,
        "ruling_raw": "",
    }
    if not lines:
        return result

    cutoff = int(len(lines) * 0.85)
    tail_text = "\n".join(lines[cutoff:])

    fallo_m = FALLO_PATTERN.search(tail_text)
    if not fallo_m:
        return result

    fallo_text = fallo_m.group(0)
    result["ruling_raw"] = fallo_text.strip()

    verbs = RULING_VERB_PATTERN.findall(fallo_text)
    result["ruling_keywords"] = [v.upper() for v in verbs]
    result["ruling_is_partial"] = bool(PARTIAL_QUALIFIER_PATTERN.search(fallo_text))

    return result


# ---------------------------------------------------------------------------
# Module 6 — Legal provisions
# ---------------------------------------------------------------------------

def extract_provisions(text: str) -> dict:
    """
    Extract cited legal provisions and collect canonical law names.

    Scans both structured cites (Article X of the Family Code) and
    statute shortcuts (RA 9165). Merges and deduplicates.
    """
    result: dict = {"cited_provisions": [], "canonical_laws": []}
    if not text:
        return result

    provisions: list[dict] = []

    # Structured cites
    for m in PROVISION_LAW_PATTERN.finditer(text):
        cite = m.group(0).strip()
        provisions.append({"cite": cite, "source_law": _canonical_law(cite)})

    # Statute shortcuts — e.g. "RA 9165", "Republic Act 9165"
    for m in STATUTE_PATTERN.finditer(text):
        ra_num = m.group(1)
        cite = m.group(0).strip()
        provisions.append({"cite": cite, "source_law": f"REPUBLIC ACT NO. {ra_num}"})

    # Deduplicate by cite text
    seen_cites: set[str] = set()
    unique: list[dict] = []
    for p in provisions:
        key = p["cite"].lower()
        if key not in seen_cites:
            seen_cites.add(key)
            unique.append(p)

    # Collect canonical law names
    laws_seen: set[str] = set()
    for p in unique:
        law = p["source_law"]
        if law not in laws_seen:
            laws_seen.add(law)

    result["cited_provisions"] = unique
    result["canonical_laws"] = sorted(laws_seen)
    return result


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

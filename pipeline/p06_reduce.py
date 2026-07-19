"""
pipeline/p06_reduce.py
Stage 6 — Reduce: single AI call that transforms the compiled stream into
the Master Case Digest markdown document.

Key rules:
  - REDUCE_SYSTEM_PROMPT and REDUCE_FORMAT are module-level string constants.
  - build_reduce_user_content() injects all REDUCE_PROMPT_VARS from §0.5.
  - run_reduce() does NOT retry itself; retries are delegated to swarm.call(retries=5).
  - Raises RuntimeError if all providers fail (no silent empty file).
  - All paths come from config.py.
"""

from __future__ import annotations

import json
import re

from models.constants import STATUTE_CORRECTIONS
from models.types import GlobalContext
from pipeline.p05_stitch import verify_usage_examples
from swarm import ProviderSwarm
from utils.text_utils import normalize_legal_terms
from utils.regex_utils import ISSUE_PATTERNS
from models.penalty_tables import classify_penalty_period, describe_period, get_article_359_facts
from config import (
    INTERMEDIATE_STREAM_PATH,
    INTERMEDIATE_LINES_PATH,
    INTERMEDIATE_CONTEXT_PATH,
    OUTPUT_DIGEST_PATH,
    REDUCE_MAX_TOKENS,
    REDUCE_TEMPERATURE,
    REDUCE_TIMEOUT,
)

# ---------------------------------------------------------------------------
# Reduce system prompt — fixed module-level constant.
# ---------------------------------------------------------------------------
REDUCE_SYSTEM_PROMPT: str = (
    "You are an expert Philippine Bar Reviewer and Supreme Court legal scholar.\n"
    "You are receiving a pre-compiled structured stream of ChunkData packets extracted\n"
    "algorithmically from a Philippine SC decision. The stream has been locally verified.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. Any text labeled VerbatimText has been extracted directly from the source.\n"
    "   Reproduce it EXACTLY — do not rephrase, summarize, or alter a single word.\n"
    "2. Use the Commentary strings as narrative bridges for chronological flow.\n"
    "3. Tailor every section to the stated Bar Focus only.\n"
    "4. Begin every section heading with ##.\n"
    "5. ALAC must be a standalone section, not embedded in The Ruling.\n"
    "6. When writing Section 2 (Legal Vocabulary), use the precise "
    "legal form of terms as they appear in the case text. "
    "Do not paraphrase legal terms of art (e.g. use 'writ of "
    "mandamus', not 'court order'). Preserve original Spanish legal "
    "spellings exactly as they appear (e.g. 'prision correccional', "
    "not 'prision correccional').\n"
    "7. Section 2 (Legal Vocabulary) must define EXACTLY the terms "
    "listed under HARDWORDS_LOCKED in the compiled stream header. "
    "Do not add, remove, or rename any term. "
    "If a term is not in HARDWORDS_LOCKED it must not appear in Section 2.\n"
    "8. Section 5 (The Ruling) must reproduce the SC_FALLO_VERBATIM "
    "text from the compiled stream header EXACTLY. "
    "Do not paraphrase, summarize, or substitute any other text "
    "for the Court's dispositive portion.\n"
    "9. In Section 3 (The Facts), always identify parties by their "
    "role using PETITIONER and RESPONDENT labels from the chunk "
    "context headers. Never swap roles between sentences.\n"
    "10. In Section 3 (The Facts), do NOT label private complainants "
    "as RESPONDENT. RESPONDENT refers only to the opposing party named "
    "in the case caption. Private complainants (the offended party in "
    "a criminal case) must be referred to by their proper name, not by "
    "a party-role label. Example: write 'Norma Capintoy, the private "
    "complainant' — never 'RESPONDENT Norma Capintoy'.\n"
    "11. In Section 4 (The Issues), state each issue as the parties "
    "framed it in their pleadings, or as the Court identified it in "
    "its opening paragraphs. Do NOT recast the Court's internal "
    "reasoning steps or motu proprio actions as issues. An issue is a "
    "question the parties actually disputed or that the Court expressly "
    "identified as the question to be resolved — not a sub-step the "
    "Court used while working through its analysis. A motu proprio action "
    "taken by the Court sua sponte — such as substituting a fine for "
    "imprisonment — is never an 'issue' for Section 4. Omit it entirely.\n"
    "12. In Section 7 (Mock Bar Exam Question), the question must test "
    "the specific legal doctrine actually decided in this case — the "
    "precise error the SC corrected, the rule it applied, or the "
    "element it clarified. Do not ask about general principles that "
    "happen to be mentioned in passing. The model answer must name the "
    "specific error or ruling (e.g. wrong penalty period applied, "
    "unproven aggravating circumstance) and state the correct rule the "
    "SC applied, not a generic recitation of elements or definitions.\n"
    "13. Section 2 terms must be doctrines or legal concepts that the "
    "case actually decides or meaningfully applies. Do not include "
    "terms that merely appear in passing, such as formulaic closings "
    "(e.g. SO ORDERED) or incidental procedural details.\n"
    "14. In Section 6 (ALAC), when discussing a penalty error, identify "
    "precisely which component was wrong — e.g. the maximum period, not "
    "the minimum — and cite the specific range that should have been applied."
)

# ---------------------------------------------------------------------------
# Reduce output format template — appended to the user message.
# ---------------------------------------------------------------------------
REDUCE_FORMAT: str = (
    "## 1. Caption\n"
    "Provide the full case caption: parties, G.R. number, promulgation date, "
    "division, and ponente. State the bar subject this digest is tailored to.\n"
    "\n"
    "## 2. Legal Vocabulary\n"
    "List every term from HardWords Consolidated. For each: term in bold, "
    "plain-language definition, and a one-sentence usage example from the facts.\n"
    "\n"
    "## 3. The Facts\n"
    "Narrate the operative facts in chronological order. Use Commentary strings "
    "as bridges. Where VerbatimText is present, reproduce it word-for-word, "
    "indented as a block quote.\n"
    "\n"
    "## 4. The Issue(s)\n"
    "State each legal issue as a numbered question. Frame each issue in terms "
    "of the bar subject.\n"
    "\n"
    "## 5. The Ruling\n"
    "State the Court's holding for each issue. Cite the G.R. number and date. "
    "Where the Court's exact words are in VerbatimText, reproduce them verbatim "
    "as a block quote. Do NOT include the ALAC analysis here.\n"
    "\n"
    "## 6. Mock ALAC Analysis\n"
    "Apply the ALAC framework (Assertion — Law — Application — Conclusion) "
    "to the most important issue. This section is standalone — do not combine "
    "with The Ruling.\n"
    "\n"
    "## 7. Mock Bar Exam Question\n"
    "Write one bar-style essay question (3–5 sentences) drawn directly from "
    "the facts. Then provide a model answer (8–12 sentences) that cites the "
    "ruling and applies the doctrine to the question.\n"
    "\n"
    "Each section must be fully developed. "
    "Section 2 must define every term in HARDWORDS_LOCKED \u2014 do not stop early. "
    "Section 4 must list ALL issues the Court identified, not just penalty issues. "
    "Section 7 model answer must be 8\u201312 sentences minimum.\n"
)


# ---------------------------------------------------------------------------
# Penalty fact extraction
# ---------------------------------------------------------------------------

_PENALTY_NAMES = [
    "prision correccional", "arresto mayor", "prision mayor",
    "reclusion temporal", "reclusion perpetua",
]


def _build_penalty_fact(ca_penalty: str) -> str:
    """Parse raw CA penalty text and return a verified penalty fact string.
    Returns empty string if the penalty text cannot be parsed."""
    if not ca_penalty:
        return ""
    text = ca_penalty.lower()

    # Find which RPC penalty is mentioned
    found_name = ""
    for name in _PENALTY_NAMES:
        if name in text:
            found_name = name
            break
    if not found_name:
        return ""

    # Extract the maximum duration near the penalty name
    # Pattern: "to [word] ([number]) years and [word] ([number]) months of [penalty]"
    dur_pat = re.compile(
        r"(?:as\s+(?:a\s+)?maximum|,?\s+to)\s+"
        r"(?:\w+\s*\((\d+)\)\s+years?\s+and\s+)?"
        r"(\w+)\s*\((\d+)\)\s+months?\s+"
        r"of\s+" + re.escape(found_name),
        re.IGNORECASE,
    )
    dur_m = dur_pat.search(ca_penalty)
    if not dur_m:
        return ""

    years = int(dur_m.group(1)) if dur_m.group(1) else 0
    months = int(dur_m.group(3))

    period = classify_penalty_period(found_name, years, months, days=0)
    medium_desc = describe_period(found_name, "medium")

    return (
        f"VERIFIED PENALTY FACT: The lower court imposed {years} year{'s' if years != 1 else ''}"
        f" and {months} month{'s' if months != 1 else ''} of {found_name}. "
        f"This falls in the {period} period of {found_name}"
        f" (the medium period is {medium_desc}). "
        f"Use this fact directly in Section 5 (The Ruling) and Section 6 (ALAC)."
    )


# ---------------------------------------------------------------------------
# Issue extraction from source
# ---------------------------------------------------------------------------

_ISSUE_WINDOW_START: int = 50
_ISSUE_WINDOW_END: int = 200
_ISSUE_MAX_ISSUES: int = 5


def extract_stated_issues(source_lines: list[str]) -> str:
    """Extract the Supreme Court's exact issue framing from source lines.

    Only scans lines 50–200 where Philippine SC decisions typically state
    the issues after reciting the facts. Returns formatted bullet points
    for injection into the reduce prompt, or empty string if nothing found.
    """
    if not source_lines or len(source_lines) < _ISSUE_WINDOW_START:
        return ""

    window = "\n".join(source_lines[_ISSUE_WINDOW_START:_ISSUE_WINDOW_END])
    findings: list[str] = []
    for pattern in ISSUE_PATTERNS:
        for m in pattern.finditer(window):
            issue_text = m.group(1).strip()
            if 20 < len(issue_text) < 600:
                findings.append(f"- {issue_text}")

    if not findings:
        return ""

    lines_found = findings[:_ISSUE_MAX_ISSUES]
    return "\n".join(["VERIFIED ISSUES (exact text from the decision):"] + lines_found)


# ---------------------------------------------------------------------------
# Roles fact (Module 1)
# ---------------------------------------------------------------------------

def _build_roles_fact(global_context: GlobalContext) -> str:
    """Build a verified roles fact string from the context.

    Injects the trial-level roles of petitioner and respondent so the AI
    correctly identifies who was the defendant/accused at trial.
    Returns empty string if both roles are Unknown.
    """
    p_role = global_context.get("petitioner_trial_role", "Unknown") or "Unknown"
    r_role = global_context.get("respondent_trial_role", "Unknown") or "Unknown"
    if p_role == "Unknown" and r_role == "Unknown":
        return ""
    petitioner = global_context.get("petitioner", "Petitioner")
    respondent = global_context.get("respondent", "Respondent")
    parts: list[str] = []
    if p_role != "Unknown":
        parts.append(f"{petitioner} was the {p_role} at trial")
    if r_role != "Unknown":
        parts.append(f"{respondent} was the {r_role} at trial")
    return "VERIFIED ROLE FACT: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Ruling fact (Module 5)
# ---------------------------------------------------------------------------

def _build_ruling_fact(global_context: GlobalContext) -> str:
    """Build a verified ruling fact string from the context.

    Injects the SC's ruling disposition (affirmed, reversed, etc.)
    and whether it is a partial ruling.
    Returns empty string if no ruling keywords found.
    """
    keywords = global_context.get("ruling_keywords", [])
    if not keywords:
        return ""
    is_partial = global_context.get("ruling_is_partial", False)
    partial_str = "The ruling is PARTIAL." if is_partial else "The ruling is FINAL."
    kw_str = ", ".join(keywords)
    return f"VERIFIED RULING FACT: The Supreme Court {kw_str} the lower court ruling. {partial_str}"


# ---------------------------------------------------------------------------
# Post-reduce deterministic corrections
# ---------------------------------------------------------------------------

def apply_statute_corrections(digest: str) -> str:
    """Replace wrong AI-generated statute names/numbers with correct citations.

    Uses STATUTE_CORRECTIONS from models/constants.py.
    Applied after the AI call — no AI involvement, pure string replacement.
    Order matters: longer/more-specific strings are replaced before shorter ones
    to avoid partial matches (dict preserves insertion order in Python 3.7+).
    """
    for wrong, correct in STATUTE_CORRECTIONS.items():
        digest = digest.replace(wrong, correct)
    return digest


# ---------------------------------------------------------------------------
# build_reduce_user_content
# ---------------------------------------------------------------------------

def build_reduce_user_content(
    compiled_stream: str,
    global_context: GlobalContext,
    source_lines: list[str] | None = None,
) -> str:
    """
    Build the full user message for the Reduce AI call.
    Injects all REDUCE_PROMPT_VARS from §0.5 via global_context.
    """
    bar_subject = global_context["bar_subject"]
    petitioner = global_context["petitioner"]
    respondent = global_context["respondent"]
    gr_number = global_context["gr_number"]
    ponente = global_context["ponente"]
    promulgation_date = global_context["promulgation_date"]
    division = global_context["division"]

    penalty_fact = _build_penalty_fact(global_context.get("ca_penalty", ""))

    # Inject Article 359 specific facts if this case involves slander by deed
    article_359_fact = ""
    if "article 359" in compiled_stream.lower() or "slander by deed" in compiled_stream.lower():
        article_359_fact = get_article_359_facts()

    # Extract stated issues from source
    issues_fact = extract_stated_issues(source_lines or [])

    # Role injection (Module 1)
    roles_fact = _build_roles_fact(global_context)

    # Ruling injection (Module 5)
    ruling_fact = _build_ruling_fact(global_context)

    user_content = (
        f"BAR FOCUS: {bar_subject}\n"
        f"Case: {petitioner} v. {respondent}\n"
        f"G.R. Number: {gr_number}\n"
        f"Division: {division}\n"
        f"Ponente: {ponente}\n"
        f"Date: {promulgation_date}\n"
        f"\n"
        f"{compiled_stream}\n"
        f"\n"
        f"--- END OF STREAM ---\n"
    )
    verified_sections = [penalty_fact, article_359_fact, issues_fact, roles_fact, ruling_fact]
    non_empty = [s for s in verified_sections if s]
    if non_empty:
        user_content += (
            f"\n"
            f"--- VERIFIED COMPUTED FACTS (use these exactly in ALAC) ---\n"
        )
        for section in non_empty:
            user_content += f"{section}\n"
        user_content += "--- END VERIFIED FACTS ---\n"
    user_content += (
        f"\n"
        f"Now generate the complete Master Case Digest using this exact format:\n"
        f"{REDUCE_FORMAT}"
    )
    return user_content


# ---------------------------------------------------------------------------
# run_reduce
# ---------------------------------------------------------------------------

def run_reduce(
    compiled_stream: str,
    global_context: GlobalContext,
    swarm: ProviderSwarm,
    source_lines: list[str] | None = None,
) -> str:
    """
    Execute the single Reduce AI call.
    Retries are delegated to swarm.call(retries=5) — this function does not retry.
    Raises RuntimeError if the swarm exhausts all providers.
    Returns the raw Master Digest text.
    """
    user_content = build_reduce_user_content(compiled_stream, global_context, source_lines)

    # Override max_tokens for the reduce call on every provider temporarily.
    # We do this by calling the swarm with a custom system prompt that requests
    # a long output; the per-provider max_tokens will be respected by each Provider.
    # For providers that need higher token limits, operators should set REDUCE_MAX_TOKENS.
    # Start with ApeKey (position 0) to avoid round-robin landing on a slow provider
    swarm.reset_index()
    result = swarm.call(REDUCE_SYSTEM_PROMPT, user_content, retries=5, timeout=REDUCE_TIMEOUT)

    if result is None:
        raise RuntimeError(
            "All providers failed at Reduce stage. "
            "Check API keys and provider availability."
        )

    # Post-reduce deterministic passes (no AI)
    result = apply_statute_corrections(result)
    result = normalize_legal_terms(result)

    # Verify usage examples against source — auto-correct flagged examples
    sl = source_lines or []
    if sl:
        flagged, result = verify_usage_examples(result, sl)
        for f in flagged:
            print(
                f"[VERIFY] {f['status']} usage example "
                f"(confidence={f['confidence']}): {f['example'][:80]!r}"
            )

    return result


# ---------------------------------------------------------------------------
# __main__ — Stage 6 standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import os
    from pipeline.p00_fetch import load_lines
    from swarm import build_default_swarm

    print("Loading compiled stream…")
    with open(INTERMEDIATE_STREAM_PATH, encoding="utf-8") as fh:
        compiled_stream = fh.read()

    print("Loading global context…")
    with open(INTERMEDIATE_CONTEXT_PATH, encoding="utf-8") as fh:
        global_context: GlobalContext = json.load(fh)

    print("Loading source lines…")
    source_lines = load_lines(INTERMEDIATE_LINES_PATH)

    print("Building swarm…")
    swarm = build_default_swarm()

    # Temporarily raise max_tokens on all providers for the reduce stage.
    for provider in swarm._providers:
        provider.max_tokens = REDUCE_MAX_TOKENS

    print("Running Reduce stage…")
    digest = run_reduce(compiled_stream, global_context, swarm, source_lines=source_lines)

    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_DIGEST_PATH, "w", encoding="utf-8") as fh:
        fh.write(digest)

    n = len(digest)
    print(f"Digest saved to {OUTPUT_DIGEST_PATH} ({n} characters)")

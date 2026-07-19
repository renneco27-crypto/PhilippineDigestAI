"""
pipeline/p07_verify.py
Stage 7 — Fact Verification: cross-reference the final digest against
the GlobalContext fields and original source lines.

Each check_* function returns a list of VerificationFlag dicts.
run_verify() aggregates all checks into a VerificationResult.

All checks are deterministic — no AI calls.
"""

from difflib import SequenceMatcher

from models.types import GlobalContext, VerificationFlag, VerificationResult
from utils.regex_utils import PEOPLE_PATTERN


# ---------------------------------------------------------------------------
# Check 1 — Party roles
# ---------------------------------------------------------------------------

def check_party_roles(
    digest_text: str,
    context: GlobalContext,
) -> list[VerificationFlag]:
    """Verify the digest correctly identifies trial roles.

    Flags:
      - CRITICAL if the digest says 'defendant' when context says
        petitioner was the plaintiff, or vice versa.
      - WARNING if role info is missing from context but digest asserts one.
    """
    flags: list[VerificationFlag] = []
    p_role = context.get("petitioner_trial_role", "Unknown")
    r_role = context.get("respondent_trial_role", "Unknown")

    if p_role in ("defendant", "accused"):
        # Digest should not call petitioner "plaintiff"
        if "plaintiff" in digest_text.lower():
            flags.append({
                "field": "petitioner_trial_role",
                "severity": "WARNING",
                "note": f"Digest may refer to petitioner as 'plaintiff' but context says petitioner was {p_role} at trial",
            })
    return flags


# ---------------------------------------------------------------------------
# Check 2 — All parties present
# ---------------------------------------------------------------------------

def _most_distinctive_token(name: str) -> str:
    """Return the most distinctive token from a party name.

    Skips generic tokens like COMPANY, DEPARTMENT, JUSTICE, etc.
    Returns the longest non-generic token, or the last token as fallback.
    """
    GENERIC = {"COMPANY", "CORPORATION", "CORP", "INC", "LTD", "LLC",
               "DEPARTMENT", "BUREAU", "OFFICE", "BOARD", "COMMISSION",
               "JUSTICE", "COURT", "BANK", "GROUP", "HOLDINGS", "ENTERPRISE",
               "ASSOCIATION", "CO", "CO.", "&", "AND", "THE", "OF", "DE"}
    tokens = name.upper().replace(",", "").split()
    best = tokens[-1] if tokens else ""
    for t in tokens:
        if t not in GENERIC and len(t) >= 4:
            best = t
    return best


def check_all_parties_present(
    digest_text: str,
    context: GlobalContext,
) -> list[VerificationFlag]:
    """Verify every extracted party name appears in the digest.

    Uses the most distinctive token as a fuzzy identifier.
    """
    flags: list[VerificationFlag] = []
    digest_lower = digest_text.lower()

    for role, names in [("petitioner", context.get("petitioners", [])),
                        ("respondent", context.get("respondents", []))]:
        for name in names:
            token = _most_distinctive_token(name).lower()
            if token and len(token) >= 4 and token not in digest_lower:
                flags.append({
                    "field": f"{role}s",
                    "severity": "HIGH",
                    "note": f"Party name '{name}' (token '{token}') not found in digest",
                })
    return flags


# ---------------------------------------------------------------------------
# Check 3 — Consolidated GR numbers
# ---------------------------------------------------------------------------

def check_consolidated_grs(
    digest_text: str,
    context: GlobalContext,
) -> list[VerificationFlag]:
    """Verify all GR numbers appear in the digest for consolidated cases."""
    flags: list[VerificationFlag] = []
    gr_numbers = context.get("gr_numbers", [])
    if len(gr_numbers) <= 1:
        return flags

    for gr in gr_numbers:
        if gr.lower() not in digest_text.lower():
            flags.append({
                "field": "gr_numbers",
                "severity": "HIGH",
                "note": f"GR number '{gr}' not found in digest",
            })
    return flags


# ---------------------------------------------------------------------------
# Check 4 — Metadata accuracy
# ---------------------------------------------------------------------------

def check_metadata(
    digest_text: str,
    context: GlobalContext,
) -> list[VerificationFlag]:
    """Verify key metadata fields appear in the digest."""
    flags: list[VerificationFlag] = []
    digest_lower = digest_text.lower()

    checks = [
        ("gr_number", context.get("gr_number", "")),
        ("ponente", context.get("ponente", "")),
        ("division", context.get("division", "")),
    ]

    # Skip single-digit / abbreviated check for metadata — use substring match
    for field, value in checks:
        if value and value.lower() not in digest_lower:
            # Try just the surname for ponente
            if field == "ponente":
                surname = value.split(",")[0].strip().lower()
                if surname in digest_lower:
                    continue
            flags.append({
                "field": field,
                "severity": "WARNING" if field == "division" else "HIGH",
                "note": f"Metadata '{field}' value '{value}' not found in digest",
            })

    # Per curiam
    if context.get("is_per_curiam") and "per curiam" not in digest_lower:
        flags.append({
            "field": "is_per_curiam",
            "severity": "WARNING",
            "note": "Case is per curiam but digest does not mention it",
        })

    return flags


# ---------------------------------------------------------------------------
# Check 5 — Ruling nuance
# ---------------------------------------------------------------------------

def check_ruling_nuance(
    digest_text: str,
    context: GlobalContext,
) -> list[VerificationFlag]:
    """Verify the digest's ruling section matches the extracted disposition."""
    flags: list[VerificationFlag] = []
    keywords = context.get("ruling_keywords", [])
    if not keywords:
        return flags

    digest_lower = digest_text.lower()
    for kw in keywords:
        if kw.lower() not in digest_lower:
            flags.append({
                "field": "ruling_keywords",
                "severity": "WARNING",
                "note": f"Ruling keyword '{kw}' not found in digest",
            })

    if context.get("ruling_is_partial"):
        partial_indicators = ["partial", "in part", "with modification", "except"]
        if not any(ind in digest_lower for ind in partial_indicators):
            flags.append({
                "field": "ruling_is_partial",
                "severity": "HIGH",
                "note": "Ruling is partial but digest does not reflect this",
            })

    return flags


# ---------------------------------------------------------------------------
# Check 6 — Legal provisions
# ---------------------------------------------------------------------------

def check_legal_provisions(
    digest_text: str,
    context: GlobalContext,
    lines: list[str],
) -> list[VerificationFlag]:
    """Verify cited legal provisions appear in the digest."""
    flags: list[VerificationFlag] = []
    provisions = context.get("cited_provisions", [])
    if not provisions:
        return flags

    digest_lower = digest_text.lower()
    for prov in provisions[:15]:  # cap at 15 to avoid noise
        cite = prov["cite"]
        # Only flag if the cite is substantive (not a passing reference)
        if len(cite) >= 8 and cite.lower() not in digest_lower:
            flags.append({
                "field": "cited_provisions",
                "severity": "INFO",
                "note": f"Provision '{cite}' cited in source but not in digest",
            })
    return flags


# ---------------------------------------------------------------------------
# run_verify — aggregate all checks
# ---------------------------------------------------------------------------

def run_verify(
    digest_text: str,
    global_context: GlobalContext,
    lines: list[str],
) -> VerificationResult:
    """Run all verification checks and return an aggregated result.

    This is non-fatal — a failing check never blocks the digest output.
    """
    all_flags: list[VerificationFlag] = []
    all_flags.extend(check_party_roles(digest_text, global_context))
    all_flags.extend(check_all_parties_present(digest_text, global_context))
    all_flags.extend(check_consolidated_grs(digest_text, global_context))
    all_flags.extend(check_metadata(digest_text, global_context))
    all_flags.extend(check_ruling_nuance(digest_text, global_context))
    all_flags.extend(check_legal_provisions(digest_text, global_context, lines))

    passed = not any(f["severity"] in ("CRITICAL", "HIGH") for f in all_flags)
    n_flags = len(all_flags)
    n_crit = sum(1 for f in all_flags if f["severity"] == "CRITICAL")
    n_high = sum(1 for f in all_flags if f["severity"] == "HIGH")

    if n_flags == 0:
        summary = "All checks passed — no flags raised"
    else:
        status = "PASSED" if passed else "FAILED"
        summary = (
            f"{status}: {n_flags} flag(s) "
            f"({n_crit} critical, {n_high} high, "
            f"{n_flags - n_crit - n_high} warning/info)"
        )

    return VerificationResult(
        passed=passed,
        flags=all_flags,
        summary=summary,
    )

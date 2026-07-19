# models/constants.py

KEYWORDS: dict[str, str] = {
    # ── Cross-cutting: Fallo / Dispositive ──────────────────────────────────
    "wherefore":                                    "fallo",
    "accordingly":                                  "fallo",
    "in view":                                      "fallo",
    "for these":                                    "fallo",
    "premises":                                     "fallo",
    "so ordered":                                   "fallo",
    "ordered, adjudged and decreed":                "fallo",
    "it is hereby ordered, adjudged and decreed":   "fallo",

    # ── Cross-cutting: Ruling ────────────────────────────────────────────────
    "we hold that":                                 "ruling",
    "we find that":                                 "ruling",
    "this Court holds that":                        "ruling",
    "we answer the certified question":             "ruling",
    "petition is denied":                           "ruling",
    "petition is dismissed":                        "ruling",
    "writ is denied":                               "ruling",
    "denied with finality":                         "ruling",

    # ── Cross-cutting: Doctrine ──────────────────────────────────────────────
    "doctrine of":                                  "doctrine",
    "it is settled that":                           "doctrine",
    "it is settled rule that":                      "doctrine",
    "it is well settled that":                      "doctrine",
    "time and again":                               "doctrine",
    "time and again, this Court held":              "doctrine",
    "it is well established that":                  "doctrine",
    "it is axiomatic that":                         "doctrine",
    "it is elementary that":                        "doctrine",
    "in legal principle":                           "doctrine",
    "the rule is":                                  "doctrine",
    "it has been held":                             "doctrine",

    # ── Cross-cutting: Definition ────────────────────────────────────────────
    "for purposes of this Act":                     "definition",
    "for purposes of this section":                 "definition",
    "the term":                                     "definition",
    "shall mean":                                   "definition",
    "means ":                                       "definition",
    "includes":                                     "definition",
    "refers to":                                    "definition",

    # ── Cross-cutting: Procedural ────────────────────────────────────────────
    "motion for reconsideration":                   "procedural",
    "motion to dismiss":                            "procedural",
    "motion to quash":                              "procedural",
    "petitioner filed a petition for certiorari":   "procedural",
    "petition for certiorari":                      "procedural",
    "petition for prohibition":                     "procedural",
    "petition for mandamus":                        "procedural",
    "certiorari":                                   "procedural",
    "mandamus":                                     "procedural",
    "prohibition":                                  "procedural",
    "quo warranto":                                 "procedural",
    "Notice of Appeal":                             "procedural",
    "appeal is dismissed":                          "procedural",
    "lack of jurisdiction":                         "procedural",
    "grave abuse of discretion":                    "procedural",
    "manifest injustice":                           "procedural",
    "new matter":                                   "procedural",

    # ── Political & International Law ────────────────────────────────────────
    "due process of law":                           "Political & International Law",
    "equal protection of the laws":                 "Political & International Law",
    "bill of rights":                               "Political & International Law",
    "ex post facto":                                "Political & International Law",
    "bill of attainder":                            "Political & International Law",
    "political question":                           "Political & International Law",
    "executive privilege":                          "Political & International Law",
    "sovereign immunity":                           "Political & International Law",
    "diplomatic immunity":                          "Political & International Law",
    "Vienna Convention on Diplomatic Relations":    "Political & International Law",
    "international law":                            "Political & International Law",
    "acts performed in an official capacity":       "Political & International Law",
    "par in parem non habet imperium":              "Political & International Law",
    "international comity":                         "Political & International Law",
    "Extradition treaty":                           "Political & International Law",

    # ── Labor Law & Social Legislation ──────────────────────────────────────
    "illegal dismissal":                            "Labor Law & Social Legislation",
    "illegal dismissal case":                       "Labor Law & Social Legislation",
    "illegal dismissal cases":                      "Labor Law & Social Legislation",
    "security of tenure":                           "Labor Law & Social Legislation",
    "just or authorized cause":                     "Labor Law & Social Legislation",
    "probationary employment":                      "Labor Law & Social Legislation",
    "substantial evidence":                         "Labor Law & Social Legislation",
    "onus probandi rests on the employer":          "Labor Law & Social Legislation",
    "burden of proof is on the employer":           "Labor Law & Social Legislation",
    "employer bears the burden of proving":         "Labor Law & Social Legislation",
    "prima facie case":                             "Labor Law & Social Legislation",
    "Labor Code":                                   "Labor Law & Social Legislation",
    "household employee":                           "Labor Law & Social Legislation",
    "Social Security System":                       "Labor Law & Social Legislation",
    "PhilHealth":                                   "Labor Law & Social Legislation",
    "poverty alleviation":                          "Labor Law & Social Legislation",
    "4Ps":                                          "Labor Law & Social Legislation",

    # ── Civil Law ────────────────────────────────────────────────────────────
    "contract of sale":                             "Civil Law",
    "stipulations is illegal":                      "Civil Law",
    "enormous lesio":                               "Civil Law",
    "usucapion":                                    "Civil Law",
    "Article 1305":                                 "Civil Law",
    "forced marriage":                              "Civil Law",
    "legal capacity":                               "Civil Law",
    "ground for annulment":                         "Civil Law",
    "just and legal cause":                         "Civil Law",
    "psychological incapacity":                     "Civil Law",
    "marriage shall be dissolved":                  "Civil Law",
    "legitimated children":                         "Civil Law",
    "dissolution of marriage":                      "Civil Law",

    # ── Taxation Law ────────────────────────────────────────────────────────
    "Internal Revenue Code":                        "Taxation Law",
    "gross income":                                 "Taxation Law",
    "income tax":                                   "Taxation Law",
    "value-added tax":                              "Taxation Law",
    "percentage tax":                               "Taxation Law",
    "withholding tax":                              "Taxation Law",
    "tax exemption":                                "Taxation Law",
    "gross receipts tax":                           "Taxation Law",
    "VATable transaction":                          "Taxation Law",
    "transfer pricing":                             "Taxation Law",
    "tax amnesty":                                  "Taxation Law",
    "deficiency tax":                               "Taxation Law",
    "capital gains tax":                            "Taxation Law",
    "excise tax":                                   "Taxation Law",

    # ── Mercantile Law ───────────────────────────────────────────────────────
    "Articles of Incorporation":                    "Mercantile Law",
    "Articles of Partnership":                      "Mercantile Law",
    "corporation code":                             "Mercantile Law",
    "close corporation":                            "Mercantile Law",
    "corporate veil":                               "Mercantile Law",
    "piercing the corporate veil":                  "Mercantile Law",
    "letter of credit":                             "Mercantile Law",
    "bill of lading":                               "Mercantile Law",
    "carrier's lien":                               "Mercantile Law",
    "negotiable instrument":                        "Mercantile Law",
    "holder in due course":                         "Mercantile Law",
    "capital stock":                                "Mercantile Law",
    "proxy":                                        "Mercantile Law",
    "dividend":                                     "Mercantile Law",

    # ── Criminal Law ────────────────────────────────────────────────────────
    "beyond reasonable doubt":                      "Criminal Law",
    "probable cause":                               "Criminal Law",
    "qualified theft":                              "Criminal Law",
    "homicide":                                     "Criminal Law",
    "parricide":                                    "Criminal Law",
    "treason":                                      "Criminal Law",
    "writ of habeas corpus":                        "Criminal Law",
    "qualified bribery":                            "Criminal Law",
    "money laundering":                             "Criminal Law",
    "child abuse":                                  "Criminal Law",

    # ── Remedial Law ────────────────────────────────────────────────────────
    "forum shopping":                               "Remedial Law",
    "misjoinder of causes":                         "Remedial Law",
    "litis pendentia":                              "Remedial Law",
    "res judicata":                                 "Remedial Law",
    "collateral estoppel":                          "Remedial Law",
    "demurrer to evidence":                         "Remedial Law",
    "rules of court":                               "Remedial Law",
    "writ of summons":                              "Remedial Law",

    # ── Legal Ethics & Practical Exercises ──────────────────────────────────
    "Code of Professional Responsibility":          "Legal Ethics & Practical Exercises",
    "attorney-client privilege":                    "Legal Ethics & Practical Exercises",
    "conflict of interest":                         "Legal Ethics & Practical Exercises",
    "Mandatory Continuing Legal Education":         "Legal Ethics & Practical Exercises",
    "accountability":                               "Legal Ethics & Practical Exercises",
    "integrity":                                    "Legal Ethics & Practical Exercises",
    "competence":                                   "Legal Ethics & Practical Exercises",
    "due diligence":                                "Legal Ethics & Practical Exercises",
}


# ── Boilerplate patterns ─────────────────────────────────────────────────────
# Raw regex strings used by is_boilerplate_line() in utils/text_utils.py
# These lines are stripped before pipeline processing begins.

BOILERPLATE_PATTERNS: list[str] = [
    r"^Page \d+ of \d+$",
    r"^- \d+ -$",
    r"^\d+$",
    r"^Republic of the Philippines$",
    r"^Supreme Court$",
    r"^(Manila|Baguio|Cebu|Davao|Cagayan de Oro)$",
    r"^(EN BANC|FIRST DIVISION|SECOND DIVISION|THIRD DIVISION|SPECIAL FIRST DIVISION)$",
    r"^RESOLUTION$",
    r"^D E C I S I O N$",
    r"^DECISION$",
    r"^Footnotes?$",
    r"^\s*\[\d+\]\s*$",
    r"^https?://",
    r"^www\.",
    r"^E-library",
    r"^ChanRobles",
    r"^lawphil\.net",
    r"^\s*x\s*[-–]\s*x\s*[-–]\s*x\s*$",
    r"^\s*[-–]+\s*$",
]


# ── ChunkData field names ────────────────────────────────────────────────────
# Ordered list matching the <ChunkData> XML tags used in p04_map.py
# and the ChunkDataPacket TypedDict in models/types.py.
# Do not reorder — order matches the AI prompt template.

CHUNK_DATA_FIELDS: list[str] = [
    "Names",
    "Dates",
    "RootDispute",
    "ProceduralAction",
    "OperativeFacts",
    "HardWords",
    "Commentary",
    "VerbatimText",
    "SourceLines",
    "Keyword",
    "Category",
]


# ── Statute name corrections ─────────────────────────────────────────────────
# Maps wrong AI-generated statute strings to their correct RPC/Philippine citations.
# Applied as a deterministic post-reduce string replacement — no AI involvement.
# Keys are case-sensitive; apply with str.replace() in order.

STATUTE_CORRECTIONS: dict[str, str] = {
    # Indeterminate Sentence Law — commonly hallucinated as RA 7360
    "Republic Act No. 7360":            "Act No. 4103",
    "Republic Act 7360":                "Act No. 4103",
    "RA 7360":                          "Act No. 4103",
    "R.A. 7360":                        "Act No. 4103",
    "R.A. No. 7360":                    "Act No. 4103",
    "RA No. 7360":                      "Act No. 4103",
    # Correct form variants that still need normalizing
    "Republic Act No. 4103":            "Act No. 4103",
    "Republic Act 4103":                "Act No. 4103",
    "RA 4103":                          "Act No. 4103",
    # Revised Penal Code — sometimes cited as RA 3815 or misspelled
    "Republic Act No. 3815":            "Act No. 3815 (Revised Penal Code)",
    "RA 3815":                          "Act No. 3815 (Revised Penal Code)",
    # Rules of Court
    "Republic Act No. 7160":            "Republic Act No. 7160",  # correct — no change needed
}


# ── Pipeline metadata patterns ────────────────────────────────────────────────
# Regex strings used by strip_pipeline_metadata() in p05_stitch.py.
# These patterns match lines that are pipeline-internal labels, never case text.
# Compiled once at import time in p05_stitch.py.

PIPELINE_METADATA_PATTERNS: list[str] = [
    r"^This chunk occurs when",                       # context header prefix
    r"\(.*?Chunk\s+\d+.*?\)",                         # (Chunk 1 & 2), (Chunk 8)
    r"\(SC_FALLO_VERBATIM\s*[–\-]\s*Chunk.*?\)",      # (SC_FALLO_VERBATIM – Chunk 8)
    r"\(Excerpt from.*?Chunk.*?\)",                   # (Excerpt from CA decision – Chunk 1)
    r"^\s*This establishes",                          # "This establishes..." context lines
]


# ── Bar subjects ─────────────────────────────────────────────────────────────
# Canonical strings used in the selectbox (ui/app.py) and CLI (run.py).
# Must match §0.8 of the Source of Truth Registry exactly.

BAR_SUBJECTS: list[str] = [
    "Political & International Law",
    "Labor Law & Social Legislation",
    "Civil Law",
    "Taxation Law",
    "Mercantile Law",
    "Criminal Law",
    "Remedial Law",
    "Legal Ethics & Practical Exercises",
]

"""
config.py — API keys, path constants, and runtime tuning parameters.
All pipeline stages import from here. Never hardcode paths or numeric values elsewhere.
Keys are loaded from a .env file via python-dotenv (see .env.example for the template).
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── API Keys (set these in .env — never commit real keys) ───────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "your-groq-api-key-here")
MISTRAL_API_KEY: str = os.getenv("MISTRAL_API_KEY", "your-mistral-api-key-here")
NVIDIA_API_KEY: str = os.getenv("NVIDIA_API_KEY", "your-nvidia-api-key-here")
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "your-openrouter-api-key-here")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "your-gemini-api-key-here")
APEKEY_API_KEY: str = os.getenv("APEKEY_API_KEY", "")

# ── Tuning Parameters ────────────────────────────────────────────────────────
DEFAULT_WINDOW: int = 70          # Lines on each side of a keyword hit
DEFAULT_MIN_GAP: int = 40         # Minimum lines between deduplicated hits
VERBATIM_WINDOW: int = 5          # Lines for pre_extract_verbatim()
VERBATIM_THRESHOLD: float = 0.80  # Fuzzy match minimum similarity

MAP_MAX_TOKENS: int = 800         # Max output tokens per Map AI call
REDUCE_MAX_TOKENS: int = 6000     # Max output tokens for Reduce AI call
MAP_TEMPERATURE: float = 0.1
REDUCE_TEMPERATURE: float = 0.2
REDUCE_TIMEOUT: int = 40       # Timeout in seconds for the Reduce AI call (6000-token generation needs ~30-60s)

# ── Intermediate & Output File Paths ────────────────────────────────────────
INTERMEDIATE_DIR: str = "intermediate"
INTERMEDIATE_LINES_PATH: str = "intermediate/case_lines.txt"
INTERMEDIATE_CONTEXT_PATH: str = "intermediate/global_context.json"
INTERMEDIATE_HITS_PATH: str = "intermediate/hits.json"
INTERMEDIATE_PAYLOADS_PATH: str = "intermediate/chunk_payloads.json"
INTERMEDIATE_PACKETS_PATH: str = "intermediate/chunk_data_packets.json"
INTERMEDIATE_STREAM_PATH: str = "intermediate/compiled_stream.txt"
FETCH_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}
FETCH_TIMEOUT: int = 30

OUTPUT_DIGEST_PATH: str = "output/master_digest.md"

# ── Verification Output Paths ──────────────────────────────────────────────
INTERMEDIATE_VERIFY_PATH: str = "intermediate/verification.json"
OUTPUT_VERIFY_REPORT_PATH: str = "output/verification_report.txt"

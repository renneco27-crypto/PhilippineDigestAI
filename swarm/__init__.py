"""
swarm/__init__.py
Public surface for the swarm package.

Exports:
    Provider          — single API endpoint wrapper
    ProviderSwarm     — multi-provider load balancer
    build_default_swarm() — factory that reads keys from config.py
"""

from swarm.provider import Provider, ApeKeyProvider
from swarm.swarm import ProviderSwarm

import config


def build_default_swarm() -> ProviderSwarm:
    """
    Construct a ProviderSwarm from five providers.
    API keys are read from config.py constants — not from os.environ.
    """
    providers = [
        ApeKeyProvider(
            name="ApeKey",
            api_url="https://apekey.ai/v1/chat/completions",
            api_key=config.APEKEY_API_KEY,
            model="auto",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=30,
            timeout=5,
            prefer="speed",
        ),
        Provider(
            name="Groq",
            api_url="https://api.groq.com/openai/v1/chat/completions",
            api_key=config.GROQ_API_KEY,
            model="openai/gpt-oss-120b",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=30,
        ),
        Provider(
            name="Gemini",
            api_url=(
                "https://generativelanguage.googleapis.com"
                "/v1beta/openai/chat/completions"
            ),
            api_key=config.GEMINI_API_KEY,
            model="gemini-3.5-flash",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=15,
        ),
        Provider(
            name="Mistral",
            api_url="https://api.mistral.ai/v1/chat/completions",
            api_key=config.MISTRAL_API_KEY,
            model="mistral-medium-3-5",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=20,
        ),
        Provider(
            name="NVIDIA",
            api_url="https://integrate.api.nvidia.com/v1/chat/completions",
            api_key=config.NVIDIA_API_KEY,
            model="meta/llama-3.3-70b-instruct",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=20,
        ),
        Provider(
            name="OpenRouter",
            api_url="https://openrouter.ai/api/v1/chat/completions",
            api_key=config.OPENROUTER_API_KEY,
            model="openai/gpt-oss-20b:free",
            max_tokens=config.MAP_MAX_TOKENS,
            rpm_limit=20,
        ),
    ]
    return ProviderSwarm(providers)


# ---------------------------------------------------------------------------
# Quick smoke-test: python -m swarm
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("Building default swarm…")
    swarm = build_default_swarm()
    result = swarm.call("You are a test node.", "Reply with exactly: OK")
    print("Swarm test result:", result)

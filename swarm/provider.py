"""
swarm/provider.py
Provider dataclass — one per API endpoint.
Uses only the requests library. No provider SDKs.
"""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

# Import tuning constants from config (avoids circular imports)
from config import MAP_MAX_TOKENS, MAP_TEMPERATURE


@dataclass
class Provider:
    name: str
    api_url: str
    api_key: str
    model: str
    max_tokens: int = MAP_MAX_TOKENS
    rpm_limit: int = 20
    timeout: int = 20
    last_request_time: float = field(default_factory=time.time)
    failures: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)

    def throttle(self) -> None:
        """Enforce per-provider rate limit. Blocks until safe to call."""
        min_gap = 60.0 / self.rpm_limit
        with self.lock:
            elapsed = time.time() - self.last_request_time
            if elapsed < min_gap:
                time.sleep(min_gap - elapsed)
            self.last_request_time = time.time()

    def _build_payload(self, system_prompt: str, user_content: str, max_tokens: int) -> dict:
        """Build the request payload, optionally injecting routing hints."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": max_tokens,
            "temperature": MAP_TEMPERATURE,
        }
        if hasattr(self, "prefer") and self.prefer:
            payload["routing"] = {"prefer": self.prefer}
        return payload

    def call(self, system_prompt: str, user_content: str, timeout: Optional[int] = None) -> Optional[str]:
        """
        Make one API call to an OpenAI-compatible /v1/chat/completions endpoint.
        Returns response text or None on any error.
        Retries up to 3 times with exponential backoff on HTTP 429 (rate-limit).
        """
        self.throttle()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = self._build_payload(system_prompt, user_content, self.max_tokens)
        max_429_retries = 3
        for attempt in range(max_429_retries):
            try:
                response = requests.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=timeout or self.timeout,
                )
                if response.status_code == 429 and attempt < max_429_retries - 1:
                    sleep_time = (2 ** attempt) + random.uniform(0, 1)
                    print(
                        f"[Provider:{self.name}] 429, "
                        f"retrying in {sleep_time}s "
                        f"(attempt {attempt + 2}/{max_429_retries})"
                    )
                    time.sleep(sleep_time)
                    continue
                response.raise_for_status()
                data = response.json()
                text = data["choices"][0]["message"]["content"]
                self.failures = 0
                return text
            except requests.exceptions.HTTPError as exc:
                if response.status_code == 429:
                    self.failures += 1
                    print(
                        f"[Provider:{self.name}] 429 exhausted retries "
                        f"(failures={self.failures}): {exc}"
                    )
                    return None
                self.failures += 1
                print(
                    f"[Provider:{self.name}] HTTP {response.status_code} "
                    f"(failures={self.failures}): {exc}"
                )
                return None
            except Exception as exc:
                self.failures += 1
                print(f"[Provider:{self.name}] Error (failures={self.failures}): {exc}")
                return None
        self.failures += 1
        print(f"[Provider:{self.name}] 429 exhausted retries (failures={self.failures})")
        return None


@dataclass
class ApeKeyProvider(Provider):
    """Provider subclass for ApeKey, which supports routing hints."""
    prefer: str = "speed"

"""
swarm/swarm.py
ProviderSwarm — round-robin load balancer over multiple Provider instances.
Supports serial call() with fallback and parallel dispatch_parallel().
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

from swarm.provider import Provider
from models.types import SwarmTask


class ProviderSwarm:
    def __init__(self, providers: list[Provider]) -> None:
        if not providers:
            raise ValueError("ProviderSwarm requires at least one Provider.")
        self._providers: list[Provider] = providers
        self._index: int = 0
        self._lock: threading.Lock = threading.Lock()

    def _next_provider(self) -> Provider:
        """Return the next provider in round-robin order."""
        with self._lock:
            self._index += 1
            return self._providers[self._index % len(self._providers)]

    def reset_index(self) -> None:
        """Reset the round-robin index so the next call starts with provider 0 (ApeKey)."""
        with self._lock:
            self._index = -1

    def call(
        self,
        system_prompt: str,
        user_content: str,
        retries: int = 5,
        timeout: Optional[int] = None,
    ) -> Optional[str]:
        """
        Round-robin call with automatic fallback.
        Skips providers that have accumulated 5 or more consecutive failures.
        Returns the first successful response, or None if all attempts fail.
        If timeout is provided, it overrides each provider's default timeout.
        """
        tried: set[str] = set()
        for _ in range(retries):
            provider = self._next_provider()
            # Skip providers that have failed too many times recently.
            if provider.failures >= 5:
                continue
            # Avoid hitting the exact same provider twice in one call cycle
            # when retries < len(providers); still allow it if we must.
            if provider.name in tried and len(tried) < len(self._providers):
                # Try to get a different one.
                for p in self._providers:
                    if p.name not in tried and p.failures < 3:
                        provider = p
                        break
            tried.add(provider.name)
            result = provider.call(system_prompt, user_content, timeout=timeout)
            if result is not None:
                print(f"[Swarm] {provider.name} succeeded")
                return result
        return None

    def dispatch_parallel(
        self,
        tasks: list[SwarmTask],
        system_prompt: str,
        result_callback: Callable[[int, Optional[str]], None],
        batch_size: int = 12,
    ) -> dict[int, Optional[str]]:
        """
        Dispatch all tasks in concurrent batches of batch_size.
        Calls result_callback(index, response) for each completed task.
        Joins all threads before returning.
        Returns dict mapping task["index"] → response string or None.
        """
        results: dict[int, Optional[str]] = {}
        results_lock = threading.Lock()

        def _worker(task: SwarmTask) -> None:
            idx = task["index"]
            response = self.call(system_prompt, task["content"])
            with results_lock:
                results[idx] = response
            result_callback(idx, response)

        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i + batch_size]
            threads: list[threading.Thread] = []
            for task in batch:
                t = threading.Thread(target=_worker, args=(task,), daemon=True)
                threads.append(t)
                t.start()
            for t in threads:
                t.join()

        return results

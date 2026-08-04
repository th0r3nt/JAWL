"""
API Key Rotator Module.

Provides high availability for LLM API calls by automatically rotating
API keys when encountering rate limits (HTTP 429) or invalid keys (HTTP 401).
Uses a Round-Robin strategy to balance the load across available keys.
"""

import math
import time
from typing import List, Dict

from src.utils.logger import main_logger
from src.l3_agent.llm.exceptions import AllKeysExhaustedError


class APIKeyRotator:
    """
    API key rotator for LLM.
    Tracks dead keys and temporary cooldowns (Rate Limits).
    """

    def __init__(self, keys: List[str]) -> None:
        """
        Initializes the rotator with a pool of keys.

        Args:
            keys: List of raw API keys from .env.

        Raises:
            ValueError: If the key list is empty.
        """

        if not keys:
            main_logger.error("[System] Empty key list passed for LLM.")
            raise ValueError("LLM API keys not found. Check your .env file.")

        self.keys = keys
        # Stores the timestamp until which a key is unavailable due to Rate Limit
        self._cooldowns: Dict[str, float] = {k: 0.0 for k in self.keys}
        self._current_index: int = 0

        main_logger.info(f"[LLM] APIKeyRotator initialized. Keys in pool: {len(self.keys)}.")

    def get_next_key(self) -> str:
        """
        Retrieves the next available key (Round-Robin), bypassing those
        in a cooldown state (Rate Limit).

        Returns:
            str: A valid API key.

        Raises:
            ValueError: If the key list is empty (all keys banned).
            AllKeysExhaustedError: If all keys are currently cooling down.
        """

        if not self.keys:
            raise ValueError("API key list is empty (or all keys have been banned).")

        now = time.time()
        attempts = len(self.keys)

        # Look for the first available key not in cooldown
        for _ in range(attempts):
            key = self.keys[self._current_index]
            self._current_index = (self._current_index + 1) % len(self.keys)

            if self._cooldowns.get(key, 0.0) <= now:
                return key

        # If we reached here, all keys are cooling down
        # Find the one that will become available first
        soonest_key = min(self.keys, key=lambda k: self._cooldowns.get(k, 0.0))
        wait_time = max(1, math.ceil(self._cooldowns[soonest_key] - now))
        raise AllKeysExhaustedError(wait_time=wait_time)

    def ban_key(self, key: str) -> None:
        """
        Removes a key from rotation permanently (e.g., on HTTP 401).

        Args:
            key: The invalid API key.
        """

        if key in self.keys:
            self.keys.remove(key)
            if key in self._cooldowns:
                del self._cooldowns[key]

            # Mask for logs
            masked = key[:6] + "***" if len(key) > 6 else "***"
            main_logger.warning(f"[LLM] Key {masked} removed from pool (Dead).")

            if self.keys:
                self._current_index = self._current_index % len(self.keys)

    def cooldown_key(self, key: str, seconds: int = 60) -> None:
        """
        Temporarily blocks a key from use (HTTP 429).

        Args:
            key: The API key that hit a rate limit.
            seconds: Duration in seconds to freeze the key.
        """

        if key in self.keys:
            self._cooldowns[key] = time.time() + seconds
            masked = key[:8] + "***" if len(key) > 8 else "***"

            reason = "Quota Exceeded" if seconds > 3600 else "Rate Limit"
            main_logger.warning(
                f"[LLM] Key {masked} cooled down for {seconds} sec ({reason})."
            )

    def total_keys(self) -> int:
        """
        Returns the total number of valid keys in the pool.
        """
        return len(self.keys)

"""
Custom Exceptions for the LLM Interaction Layer.

Enables strict typing of API and rotator errors without the need to parse raw
string messages, ensuring robust error handling in parent reasoning loops.
"""


class AllKeysExhaustedError(Exception):
    """
    Thrown by the rotator when all available API keys are temporarily blocked
    due to rate limits (HTTP 429 / Cooldown).
    """

    def __init__(self, wait_time: int) -> None:
        self.wait_time = wait_time
        super().__init__(
            f"All API keys have exhausted their limits. Must wait {wait_time} sec."
        )

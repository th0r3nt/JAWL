"""
Schemas and Data Structures for Subconscious Models.

Defines internal enumeration types for different background processes.
"""

from enum import Enum


class Pattern(str, Enum):
    """Available subconscious behavior patterns."""

    CONSOLIDATION = "consolidation"
    REFLECTION = "reflection"
    FORGETTING = "forgetting"

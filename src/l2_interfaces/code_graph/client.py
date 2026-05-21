"""
L2 client for the Code Graph interface.

Code graphs store dependencies, descriptions, and help understand complex codebases,
thanks to semantic vector search over relations in a deterministic graph.
"""

from typing import Any
from src.l2_interfaces.code_graph.state import CodeGraphState
from src.l2_interfaces.host.os.client import HostOSClient
from src.utils.settings import CodeGraphConfig


class CodeGraphClient:
    """Code Graph interface manager."""

    def __init__(self, state: CodeGraphState, config: CodeGraphConfig, host_os: HostOSClient):
        self.state = state
        self.config = config
        self.host_os = host_os
        self.state.is_online = True

    async def get_context_block(self, **kwargs: Any) -> str:
        """Block for the agent's system prompt."""
        desc = "Description: Parsing Python directory AST-trees and constructing dependency/relationship graphs for semantic search."
        if not self.state.is_online:
            return f"### CODE GRAPH [OFF]\n{desc}\nThe interface is disabled."

        if not self.state.active_indexes:
            return f"### CODE GRAPH [ON]\n{desc}\nNo active code base graphs were found."

        lines = ["Loaded architectural project indexes:"]
        for pid, path in self.state.active_indexes.items():
            lines.append(f"* Index ID: '{pid}' -> points to directory: '{path}'")

        return (
            f"### CODE GRAPH [ON]\n{desc}\n"
            "For semantic search and code navigation - use Index ID.\n\n"
            + "\n".join(lines)
        )
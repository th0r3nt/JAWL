"""
Client of the Meta interface.

Provides the agent with a reflection mechanism and the ability to modify its own
YAML configuration at runtime (without direct editing of host system files by the operator).
"""

import os
from pathlib import Path
from typing import Any, List
from ruamel.yaml import YAML

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.logger import main_logger


class MetaClient:
    """Manager of JAWL settings self-modification."""

    def __init__(
        self,
        agent_state: AgentState,
        event_bus: EventBus,
        settings_path: Path,
        interfaces_path: Path,
        access_level: int,
        available_models: List[str],
        custom_skills_enabled: bool,
    ) -> None:
        """
        Initializes the meta client.

        Args:
            agent_state: Agent state.
            event_bus: Event bus (to dispatch config updates).
            settings_path: Path to settings.yaml.
            interfaces_path: Path to interfaces.yaml.
            access_level: Meta access level (0 - SAFE, ..., 3 - CREATOR).
            available_models: List of allowed LLMs.
            custom_skills_enabled: Whether creating custom skills is permitted.
        """
        self.agent_state = agent_state
        self.bus = event_bus
        self.settings_path = settings_path
        self.interfaces_path = interfaces_path
        self.access_level = access_level
        self.available_models = available_models
        self.custom_skills_enabled = custom_skills_enabled

        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    async def update_yaml(self, file_path: Path, path_keys: List[str], new_value: Any) -> bool:
        """
        Universal method for deep updating of YAML files (settings or interfaces).

        Args:
            file_path: Which file to modify.
            path_keys: Path by nested keys (e.g.: ["llm", "temperature"]).
            new_value: New value.

        Returns:
            True if saved successfully, else False.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = self.yaml.load(f)

            target = data
            for key in path_keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]

            target[path_keys[-1]] = new_value

            with open(file_path, "w", encoding="utf-8") as f:
                self.yaml.dump(data, f)

            return True
        except Exception as e:
            main_logger.error(f"[Meta] Error updating {file_path.name}: {e}")
            return False

    def has_env_key(self, key_name: str) -> bool:
        """Checks if a token exists in environmental variables (e.g. 'GITHUB_TOKEN')."""
        return bool(os.getenv(key_name, "").strip())

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Context provider for ContextRegistry.
        Gives the agent the list of its meta capabilities and current Access Level.
        """
        desc = "Description: Dynamic framework configuration and custom skills."

        access_levels_desc = (
            "Existing access levels: \n"
            "- 0/SAFE: Basic settings.\n"
            "- 1/CONFIGURATOR: Memory management and advanced configuration settings.\n"
            "- 2/ARCHITECT: System and interface management.\n"
            "- 3/CREATOR: Registering custom scripts as native skills."
        )

        models_str = (
            ", ".join(self.available_models) if self.available_models else "The list is empty"
        )

        custom_status = "off"
        if self.custom_skills_enabled:
            custom_status = "on (need '3/CREATOR' access level)"

        return (
            f"### META [ON]\n"
            f"{desc}\n"
            f"* Access Level: {self.access_level} (current level) \n{access_levels_desc}\n\n"
            f"* Custom Skills: {custom_status}\n"
            f"* Available LLM models: [{models_str}]"
        )

"""
Meta Level 0 skills (SAFE).

Basic, safest system settings.
Allow the agent to modify its currently active LLM model (switch personalities/providers)
and adjust generation creativity (Temperature).
"""

from typing import Literal

from src.utils.event.registry import Events

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill


class MetaSafe:
    """Level 0 (SAFE). Basic system settings."""

    def __init__(self, meta_client: MetaClient) -> None:
        self.client = meta_client

    async def sleep(
        self,
        duration: int = 1800,
        depth: Literal["deep", "superficially"] = "deep",
    ) -> SkillResult:
        """
        Puts the agent to sleep for a specified duration with custom event sensitivity depth.

        depth: 'deep' (low event sensitivity) or 'superficially' (high event sensitivity).
        """
        if duration < 1:
            return SkillResult.fail("Error: Sleep duration must be at least 1 second.")

        if depth not in ("deep", "superficially"):
            return SkillResult.fail("Error: depth must be 'deep' or 'superficially'.")

        await self.client.bus.publish(
            Events.SYSTEM_SLEEP_REQUESTED, duration=duration, depth=depth
        )
        return SkillResult.ok(
            f"True. Engaged sleep mode for {duration} seconds (depth: '{depth}').",
            terminate_loop=True,
        )

    @skill()
    async def change_model(self, model_name: str) -> SkillResult:
        """
        Changes currently active LLM model.
        """

        if self.client.available_models and model_name not in self.client.available_models:
            return SkillResult.fail(
                f"Model '{model_name}' is unavailable. Please select from the list: {self.client.available_models}"
            )

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "main_model"], model_name
        )
        if not success:
            return SkillResult.fail("Error saving configuration file.")

        self.client.agent_state.llm_model = model_name
        return SkillResult.ok("True")

    @skill()
    async def add_available_model(self, model_name: str) -> SkillResult:
        """
        Adds new LLM model to available models list.
        """

        if model_name in self.client.available_models:
            return SkillResult.ok("True")

        new_list = list(self.client.available_models)
        new_list.append(model_name)

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "available_models"], new_list
        )
        if not success:
            return SkillResult.fail("Error updating configuration.")

        self.client.available_models = new_list
        return SkillResult.ok("True")

    @skill()
    async def remove_available_model(self, model_name: str) -> SkillResult:
        """
        Removes LLM model from available list.
        """

        if model_name not in self.client.available_models:
            return SkillResult.fail(f"Error: Model '{model_name}' is not in the list.")

        if model_name == self.client.agent_state.llm_model:
            return SkillResult.fail("Error: Cannot delete the currently active model.")

        new_list = [m for m in self.client.available_models if m != model_name]

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "available_models"], new_list
        )
        if not success:
            return SkillResult.fail("Error updating configuration.")

        self.client.available_models = new_list
        return SkillResult.ok("True")

    @skill()
    async def change_temperature(self, temperature: float) -> SkillResult:
        """
        Changes LLM generation temperature parameter.
        """

        if not 0.0 <= temperature <= 2.0:
            return SkillResult.fail("Temperature must be between 0.0 and 2.0.")

        success = await self.client.update_yaml(
            self.client.settings_path, ["llm", "temperature"], temperature
        )
        if not success:
            return SkillResult.fail("Error saving configuration.")

        self.client.agent_state.temperature = temperature
        return SkillResult.ok("True")

    @skill()
    async def set_current_goal(self, goal: str) -> SkillResult:
        """
        Sets current focus goal.
        Pins goal in system prompt to maintain context over long cycles.
        Pass empty string to clear.
        """

        clean_goal = goal.strip()
        self.client.agent_state.current_goal = clean_goal

        if clean_goal:
            return SkillResult.ok("True")
        return SkillResult.ok("True")

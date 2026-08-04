"""
Meta Level 2 skills (ARCHITECT).

System interfaces and lifecycle management.
Allows the agent to hardware-disable/enable JAWL components and initiate a reboot.
"""

from typing import Literal

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events
from src.utils.logger import main_logger


class MetaArchitect:
    """Level 2 (ARCHITECT). System lifecycle and interfaces management."""

    def __init__(self, meta_client: MetaClient) -> None:
        self.client = meta_client

    @skill()
    async def toggle_interface(
        self,
        interface: Literal[
            "host_os",
            "telegram_telethon",
            "telegram_aiogram",
            "github",
            "web_search",
            "multimodality",
            "calendar",
        ],
        state: bool,
    ) -> SkillResult:
        """
        Toggles system interfaces via YAML config.

        interface: Target module name.
        state: True to enable, False to disable.
        """

        # Mapping keys from Literal to real paths in interfaces.yaml
        ifmap = {
            "host_os": ["host", "os", "enabled"],
            "telegram_telethon": ["telegram", "telethon", "enabled"],
            "telegram_aiogram": ["telegram", "aiogram", "enabled"],
            "github": ["github", "enabled"],
            "web_search": ["web", "search", "enabled"],
            "multimodality": ["multimodality", "enabled"],
            "calendar": ["calendar", "enabled"],
        }

        path_keys = ifmap[interface]

        # Dependencies verification (.env) before enabling
        if state is True:
            if interface == "telegram_telethon" and not (
                self.client.has_env_key("TELETHON_API_ID")
                and self.client.has_env_key("TELETHON_API_HASH")
            ):
                return SkillResult.fail(
                    "Error enabling Telethon: missing TELETHON_API_ID and TELETHON_API_HASH in .env."
                )

            if interface == "telegram_aiogram" and not self.client.has_env_key(
                "AIOGRAM_BOT_TOKEN"
            ):
                return SkillResult.fail(
                    "Error enabling Aiogram: missing AIOGRAM_BOT_TOKEN in .env."
                )

            if interface == "github" and not self.client.has_env_key("GITHUB_TOKEN"):
                main_logger.warning(
                    "[Meta] Github is enabled without a token (Read-Only mode with a limit of 60 requests)."
                )

        success = await self.client.update_yaml(self.client.interfaces_path, path_keys, state)
        if success:
            return SkillResult.ok("True")

        return SkillResult.fail("Error updating configuration file.")

    @skill()
    async def off_system(self, reason: str = "No reason specified") -> SkillResult:
        """
        Shuts down and completely powers off the system.
        """

        main_logger.info(f"[Meta] Shutdown requested. Reason: {reason}")
        await self.client.bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Shutdown command accepted. Stopping processes.", terminate_loop=True
        )

    @skill()
    async def reboot_system(self, reason: str = "Configuration update") -> SkillResult:
        """
        Performs full system reboot.
        """

        main_logger.info(f"[Meta] Reboot requested. Reason: {reason}")
        await self.client.bus.publish(Events.SYSTEM_REBOOT_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Reboot command accepted. Initializing reboot. I'll be back.",
            terminate_loop=True,
        )
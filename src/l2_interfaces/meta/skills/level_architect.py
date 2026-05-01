"""
Навыки Meta уровня 2 (ARCHITECT).

Управление системными интерфейсами и жизненным циклом.
Позволяет агенту аппаратно отключать/включать компоненты JAWL и инициировать ребут.
"""

from typing import Literal

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events
from src.utils.logger import system_logger


class MetaArchitect:
    """Уровень 2 (ARCHITECT). Управление жизненным циклом системы и интерфейсами."""

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
        Включает или выключает системные интерфейсы через YAML конфиг.

        Args:
            interface: Название целевого модуля (например 'github').
            state: True (включить) или False (выключить).
        """
        # Маппинг ключей из Literal на реальные пути в interfaces.yaml
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

        # Проверка зависимостей (.env) перед включением
        if state is True:
            if interface == "telegram_telethon" and not (
                self.client.has_env_key("TELETHON_API_ID")
                and self.client.has_env_key("TELETHON_API_HASH")
            ):
                return SkillResult.fail(
                    "Ошибка при включении Telethon: отсутствуют TELETHON_API_ID и TELETHON_API_HASH в .env."
                )

            if interface == "telegram_aiogram" and not self.client.has_env_key(
                "AIOGRAM_BOT_TOKEN"
            ):
                return SkillResult.fail(
                    "Ошибка при включении Aiogram: отсутствует AIOGRAM_BOT_TOKEN в .env."
                )

            if interface == "github" and not self.client.has_env_key("GITHUB_TOKEN"):
                system_logger.warning(
                    "[Meta] Github включается без токена (Read-Only режим с лимитом 60 запросов)."
                )

        success = await self.client.update_yaml(self.client.interfaces_path, path_keys, state)
        if success:
            state_str = "включен" if state else "выключен"
            return SkillResult.ok(
                f"Интерфейс '{interface}' будет {state_str}. Изменения вступят в силу только после перезагрузки."
            )

        return SkillResult.fail("Ошибка обновления файла конфигурации.")

    @skill()
    async def off_system(self, reason: str = "Без причины") -> SkillResult:
        """
        Завершает работу агента и полностью выключает систему.

        Args:
            reason: Причина выключения (останется в логах).
        """
        system_logger.info(f"[Meta] Запрошено выключение системы. Причина: {reason}")
        await self.client.bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Команда на выключение принята. Инициирована остановка процессов."
        )

    @skill()
    async def reboot_system(self, reason: str = "Обновление конфигурации") -> SkillResult:
        """
        Выполняет полную перезагрузку системы (полезно после изменения конфигов).

        Args:
            reason: Причина перезагрузки.
        """
        system_logger.info(f"[Meta] Запрошена перезагрузка системы. Причина: {reason}")
        await self.client.bus.publish(Events.SYSTEM_REBOOT_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Команда на перезагрузку принята. Инициирован ребут. I'll be back."
        )

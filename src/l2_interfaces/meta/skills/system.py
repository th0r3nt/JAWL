"""
Наследие системных навыков.
Обеспечивает поддержку выключения системы, если модуль Meta загружен
с недостаточным уровнем доступа, но выключить/перезагрузить все равно надо
(например, из консоли администратора).
"""

from src.l2_interfaces.meta.client import MetaClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.event.registry import Events
from src.utils.logger import system_logger


class MetaSystem:
    """Навыки управления жизненным циклом всей системы."""

    def __init__(self, meta_client: MetaClient) -> None:
        self.client = meta_client

    @skill()
    async def off_system(self, reason: str = "Без причины") -> SkillResult:
        """
        Завершает работу агента и полностью выключает систему.
        """
        system_logger.info(f"[Meta] Запрошено выключение системы. Причина: {reason}")

        await self.client.bus.publish(Events.SYSTEM_SHUTDOWN_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Команда на выключение принята. Инициирована остановка процессов."
        )

    @skill()
    async def reboot_system(self, reason: str = "Обновление конфигурации") -> SkillResult:
        """
        Выполняет полную перезагрузку системы.
        """
        system_logger.info(f"[Meta] Запрошена перезагрузка системы. Причина: {reason}")

        await self.client.bus.publish(Events.SYSTEM_REBOOT_REQUESTED, reason=reason)
        return SkillResult.ok(
            "Команда на перезагрузку принята. Инициирован ребут. I'll be back."
        )

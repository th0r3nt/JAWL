from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance

from src.l2_interfaces.telegram.aiogram.client import AiogramClient
from src.l2_interfaces.telegram.aiogram.events import AiogramEvents
from src.l2_interfaces.telegram.aiogram.skills.chats import AiogramChats
from src.l2_interfaces.telegram.aiogram.skills.messages import AiogramMessages
from src.l2_interfaces.telegram.aiogram.skills.moderation import AiogramModeration

if TYPE_CHECKING:
    from src.main import System


def setup_aiogram(system: "System", bot_token: str | None) -> List[Any]:
    """Инициализирует Aiogram, регистрирует скиллы и возвращает компоненты жизненного цикла."""

    if not bot_token:
        system_logger.error("[System] AIOGRAM_BOT_TOKEN не найден в .env. Aiogram отключен.")
        return []

    client = AiogramClient(bot_token=bot_token, state=system.aiogram_state)
    events = AiogramEvents(
        aiogram_client=client,
        state=system.aiogram_state,
        event_bus=system.event_bus,
    )

    # Регистрация навыков для агента
    register_instance(AiogramChats(client, system.aiogram_state))
    register_instance(AiogramMessages(client))
    register_instance(AiogramModeration(client))

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(name="aiogram", provider_func=client.get_context_block)

    system_logger.info("[System] Интерфейс Aiogram загружен.")

    return [client, events]

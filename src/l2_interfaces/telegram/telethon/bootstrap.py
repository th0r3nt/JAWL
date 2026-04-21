from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.telegram.telethon.client import TelethonClient
from src.l2_interfaces.telegram.telethon.events import TelethonEvents

from src.l2_interfaces.telegram.telethon.skills.account import TelethonAccount
from src.l2_interfaces.telegram.telethon.skills.chats import TelethonChats
from src.l2_interfaces.telegram.telethon.skills.messages import TelethonMessages
from src.l2_interfaces.telegram.telethon.skills.moderation import TelethonModeration
from src.l2_interfaces.telegram.telethon.skills.polls import TelethonPolls
from src.l2_interfaces.telegram.telethon.skills.reactions import TelethonReactions
from src.l2_interfaces.telegram.telethon.skills.admin import TelethonAdmin

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_telethon(system: "System", api_id: str | None, api_hash: str | None) -> List[Any]:
    """Инициализирует Telethon, регистрирует скиллы и возвращает компоненты жизненного цикла."""

    if not api_id or not api_hash:
        system_logger.error(
            "[System] TELETHON_API_ID или TELETHON_API_HASH не найдены в .env. Telethon отключен."
        )
        return []

    config = system.interfaces_config.telegram.telethon
    session_path = str(system.local_data_dir / "telethon" / config.session_name)

    # Приводим api_id к числу, как того требует Telethon
    clean_api_id = int(api_id) if str(api_id).isdigit() else api_id

    client = TelethonClient(
        state=system.telethon_state,
        api_id=clean_api_id,
        api_hash=api_hash,
        session_path=session_path,
        timezone=system.settings.system.timezone,
    )
    events = TelethonEvents(
        tg_client=client, state=system.telethon_state, event_bus=system.event_bus
    )

    # Регистрация навыков для агента
    register_instance(TelethonAccount(client))
    register_instance(TelethonChats(client))
    register_instance(TelethonMessages(client))
    register_instance(TelethonModeration(client))
    register_instance(TelethonPolls(client))
    register_instance(TelethonReactions(client))
    register_instance(TelethonAdmin(client))

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(
        name="telethon",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Telegram Telethon] Интерфейс загружен.")

    # Возвращаем то, что нужно запустить в главном цикле
    return [client, events]

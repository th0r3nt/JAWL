"""
Инициализатор модуля Telegram Telethon (User API).
Связывает клиент, воркер событий и 7 массивов навыков в единый узел для DI-контейнера.
"""

from typing import List, Any, TYPE_CHECKING, Optional

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


def setup_telethon(
    system: "System", api_id: Optional[str], api_hash: Optional[str]
) -> List[Any]:
    """
    Инициализирует интерфейс Telethon, настраивает локальную сессию и регистрирует навыки.

    Args:
        system (System): Главный DI-контейнер системы.
        api_id (Optional[str]): TELETHON_API_ID из конфигурации.
        api_hash (Optional[str]): TELETHON_API_HASH из конфигурации.

    Returns:
        List[Any]: Компоненты с жизненным циклом (client, events).
    """
    
    if not api_id or not api_hash:
        system_logger.error(
            "[Telegram Telethon] TELETHON_API_ID или TELETHON_API_HASH не найдены в .env. Интерфейс отключен."
        )
        return []

    config = system.interfaces_config.telegram.telethon
    session_path = str(
        system.local_data_dir / "interfaces" / "telegram" / "telethon" / config.session_name
    )

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
        tg_client=client,
        state=system.telethon_state,
        event_bus=system.event_bus,
        config=config,
    )

    # Регистрация обширного арсенала навыков для агента
    register_instance(TelethonAccount(client))
    register_instance(TelethonChats(client))
    register_instance(TelethonMessages(client))
    register_instance(TelethonModeration(client))
    register_instance(TelethonPolls(client))
    register_instance(TelethonReactions(client))
    register_instance(TelethonAdmin(client))

    # Регистрация провайдеров контекста
    system.context_registry.register_provider(
        name="telethon",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Telegram Telethon] Интерфейс загружен.")
    return [client, events]

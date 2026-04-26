from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.telegram.kurigram.client import (
    KurigramClient,
    parse_telegram_api_id,
    validate_pyrogram_session_name,
)
from src.l2_interfaces.telegram.kurigram.events import KurigramEvents

from src.l2_interfaces.telegram.kurigram.skills.account import KurigramAccount
from src.l2_interfaces.telegram.kurigram.skills.chats import KurigramChats
from src.l2_interfaces.telegram.kurigram.skills.messages import KurigramMessages
from src.l2_interfaces.telegram.kurigram.skills.moderation import KurigramModeration
from src.l2_interfaces.telegram.kurigram.skills.polls import KurigramPolls
from src.l2_interfaces.telegram.kurigram.skills.reactions import KurigramReactions
from src.l2_interfaces.telegram.kurigram.skills.admin import KurigramAdmin

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def _resolve_kurigram_session_path(system: "System", session_name: str) -> str:
    session_file = f"{session_name}.session"
    session_dir = system.local_data_dir / "kurigram"
    legacy_session_dir = system.local_data_dir / "telethon"

    if (
        not (session_dir / session_file).exists()
        and (legacy_session_dir / session_file).exists()
    ):
        return str(legacy_session_dir / session_name)

    return str(session_dir / session_name)


def setup_kurigram(system: "System", api_id: str | None, api_hash: str | None) -> List[Any]:
    """Инициализирует Kurigram User API, регистрирует скиллы и возвращает компоненты жизненного цикла."""

    if not api_id or not api_hash:
        system_logger.error(
            "[Telegram Kurigram] TELETHON_API_ID или TELETHON_API_HASH не найдены в .env. Интерфейс отключен."
        )
        return []

    config = system.interfaces_config.telegram.kurigram
    try:
        session_name = validate_pyrogram_session_name(config.session_name)
    except ValueError as e:
        system_logger.error(f"[Telegram Kurigram] Некорректный session_name: {e}")
        return []

    session_path = _resolve_kurigram_session_path(system, session_name)

    # Переменные окружения сохраняем прежними для обратной совместимости.
    try:
        clean_api_id = parse_telegram_api_id(api_id)
    except ValueError as e:
        system_logger.error(f"[Telegram Kurigram] Некорректный TELETHON_API_ID: {e}")
        return []

    client = KurigramClient(
        state=system.telegram_user_state,
        api_id=clean_api_id,
        api_hash=api_hash,
        session_path=session_path,
        timezone=system.settings.system.timezone,
    )
    events = KurigramEvents(
        tg_client=client, state=system.telegram_user_state, event_bus=system.event_bus
    )

    # Регистрация навыков для агента
    register_instance(KurigramAccount(client))
    register_instance(KurigramChats(client))
    register_instance(KurigramMessages(client))
    register_instance(KurigramModeration(client))
    register_instance(KurigramPolls(client))
    register_instance(KurigramReactions(client))
    register_instance(KurigramAdmin(client))

    # Регистрация провайдеров контекста (отдают Markdown блоки в промпт агента)
    system.context_registry.register_provider(
        name="telegram_kurigram",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Telegram Kurigram] Интерфейс загружен.")

    # Возвращаем то, что нужно запустить в главном цикле
    return [client, events]

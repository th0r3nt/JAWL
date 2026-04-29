from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.hooks.client import WebHooksClient
from src.l2_interfaces.web.hooks.events import WebHooksEvents
from src.l2_interfaces.web.hooks.skills.webhooks import WebHooksSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_hooks(system: "System", secret_token: str | None) -> List[Any]:
    """Инициализирует интерфейс Web Hooks."""

    if not secret_token:
        system_logger.error(
            "[Web Hooks] WEBHOOK_SECRET не задан в .env. Интерфейс принудительно отключен."
        )
        return []

    config = system.interfaces_config.web.hooks

    client = WebHooksClient(
        state=system.web_hooks_state, config=config, secret_token=secret_token
    )

    events = WebHooksEvents(
        client=client,
        state=system.web_hooks_state,
        event_bus=system.event_bus,
        timezone=system.settings.system.timezone,
    )

    # Регистрируем навыки для агента
    register_instance(WebHooksSkills(client))

    # Регистрируем блок в системный промпт
    system.context_registry.register_provider(
        name="web hooks",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Web Hooks] Интерфейс загружен.")

    # events содержит aiohttp сервер со своими методами start() и stop()
    return [events]

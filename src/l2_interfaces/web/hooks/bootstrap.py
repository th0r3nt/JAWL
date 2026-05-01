"""
Инициализатор интерфейса Web Hooks.

Поднимает локальный aiohttp сервер для приема внешних HTTP запросов
(интеграции GitHub Actions, Stripe, Smart Home и др.) и регистрирует
навыки для чтения payload'а внутри агента.
"""

from typing import List, Any, TYPE_CHECKING, Optional
from src.utils.logger import system_logger

from src.l2_interfaces.web.hooks.client import WebHooksClient
from src.l2_interfaces.web.hooks.events import WebHooksEvents
from src.l2_interfaces.web.hooks.skills.webhooks import WebHooksSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_hooks(system: "System", secret_token: Optional[str]) -> List[Any]:
    """
    Инициализирует интерфейс Web Hooks.

    Args:
        system (System): Главный DI-контейнер фреймворка.
        secret_token (Optional[str]): Секретный токен авторизации (WEBHOOK_SECRET из .env).

    Returns:
        List[Any]: Компоненты жизненного цикла (events - aiohttp сервер).
    """
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

    register_instance(WebHooksSkills(client))

    system.context_registry.register_provider(
        name="web hooks",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Web Hooks] Интерфейс загружен.")

    return [events]

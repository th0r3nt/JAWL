from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

if TYPE_CHECKING:
    from src.main import System

from src.l2_interfaces.reddit.client import RedditClient
from src.l2_interfaces.reddit.skills.reading import RedditReading

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection


def setup_reddit(
    system: "System", client_id: str | None, client_secret: str | None
) -> List[Any]:
    """Инициализирует Reddit-интерфейс."""

    if not client_id or not client_secret:
        system_logger.error(
            "[System] REDDIT_CLIENT_ID или REDDIT_CLIENT_SECRET не найдены. Reddit отключен."
        )
        return []

    config = system.interfaces_config.reddit

    client = RedditClient(
        config=config,
        state=system.reddit_state,
        client_id=client_id,
        client_secret=client_secret,
    )

    # Регистрируем Read-Only навыки
    register_instance(RedditReading(client))

    # Регистрируем стейт интерфейса в контексте агента
    system.context_registry.register_provider(
        name="reddit",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )

    system_logger.info("[Reddit] Интерфейс загружен.")

    # Возвращаем клиента, чтобы main.py мог вызвать client.start() и client.stop()
    return [client]

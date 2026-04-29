from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.web.rss.client import WebRSSClient
from src.l2_interfaces.web.rss.events import WebRSSEvents
from src.l2_interfaces.web.rss.skills.rss import WebRSSSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_web_rss(system: "System") -> List[Any]:
    """
    Инициализирует интерфейс Web RSS.
    """

    config = system.interfaces_config.web.rss

    client = WebRSSClient(state=system.web_rss_state, config=config)

    events = WebRSSEvents(
        client=client,
        state=system.web_rss_state,
        event_bus=system.event_bus,
    )

    register_instance(WebRSSSkills(client))

    system.context_registry.register_provider(
        name="web rss",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Web RSS] Интерфейс загружен.")

    return [events]

from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger

from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.events import EmailEvents
from src.l2_interfaces.email.skills.mail import EmailSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_email(system: "System", account: str | None, password: str | None) -> List[Any]:
    if not account or not password:
        system_logger.error(
            "[Email] EMAIL_ACCOUNT или EMAIL_PASSWORD не найдены. Интерфейс отключен."
        )
        return []

    config = system.interfaces_config.email

    # Строго берем стейт из системы
    client = EmailClient(state=system.email_state, account=account, password=password)

    events = EmailEvents(
        client=client,
        state=system.email_state,
        event_bus=system.event_bus,
        interval_sec=config.polling_interval_sec,
    )

    register_instance(EmailSkills(client))

    system.context_registry.register_provider(
        name="email", provider_func=client.get_context_block, section=ContextSection.INTERFACES
    )

    system_logger.info("[Email] Интерфейс загружен.")

    # Возвращаем клиент (для авторизации при старте) и эвент (для поллинга)
    return [client, events]

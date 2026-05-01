"""
Инициализатор интерфейса электронной почты (Email).

Собирает SMTP/IMAP клиент, регистрирует фоновый поллер для проверки инбокса
и внедряет навыки чтения/отправки писем в ядро агента.
"""

from typing import List, Any, TYPE_CHECKING, Optional
from src.utils.logger import system_logger

from src.l2_interfaces.email.client import EmailClient
from src.l2_interfaces.email.events import EmailEvents
from src.l2_interfaces.email.skills.mail import EmailSkills

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_email(
    system: "System", account: Optional[str], password: Optional[str]
) -> List[Any]:
    """
    Инициализирует интерфейс Email.

    Args:
        system (System): Главный DI-контейнер фреймворка.
        account (Optional[str]): Почтовый адрес из .env.
        password (Optional[str]): App Password (пароль приложения) из .env.

    Returns:
        List[Any]: Компоненты жизненного цикла (client, events).
    """
    if not account or not password:
        system_logger.error(
            "[Email] EMAIL_ACCOUNT или EMAIL_PASSWORD не найдены. Интерфейс отключен."
        )
        return []

    config = system.interfaces_config.email

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

    # Возвращаем клиент (для тестовой авторизации при старте) и эвент (для поллинга)
    return [client, events]

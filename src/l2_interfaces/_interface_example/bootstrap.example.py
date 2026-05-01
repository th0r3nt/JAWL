"""
Инициализатор (Bootstrap) пользовательского L2-интерфейса.

Этот файл - точка входа для вашего модуля. Здесь происходит внедрение зависимостей (DI):
мы берем L0 State, настраиваем Клиента (для API), Воркера (Events) и регистрируем Навыки (Skills).

Советы для разработчиков:
1. Не пишите здесь бизнес-логику. Bootstrap нужен только для "сборки" конструктора.
2. Для регистрации этого интерфейса в системе, вам нужно импортировать функцию `setup_example`
   внутри файла `src/l2_interfaces/initializer.py` и вызвать её, если модуль включен в YAML-конфиге (см. логику подробнее в initializer.py).
"""

from typing import List, Any, TYPE_CHECKING, Optional

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import register_instance  # noqa: F401
from src.l3_agent.context.registry import ContextSection  # noqa: F401

# В реальном коде импортируйте ваши модули:
# from src.l2_interfaces.my_module.client import MyClient
# from src.l2_interfaces.my_module.events import MyEvents
# from src.l2_interfaces.my_module.skills.tools import MySkills

if TYPE_CHECKING:
    from src.main import System


def setup_example(system: "System", api_key: Optional[str] = None) -> List[Any]:
    """
    Инициализирует интерфейс и интегрирует его в ядро JAWL.

    Args:
        system (System): Главный DI-контейнер фреймворка (через него мы получаем доступ к EventBus и State).
        api_key (Optional[str]): Пример ключа, который достается из .env файла в initializer.py.

    Returns:
        List[Any]: Список компонентов жизненного цикла (обычно это client и events),
                   у которых в main.py будут вызваны методы .start() и .stop().
    """

    if not api_key:
        system_logger.error("[Example] Ключ API не найден. Интерфейс принудительно отключен.")
        return []

    # 1. Создаем стейт.
    # В реальном коде вы должны создать стейт в src/l0_state/interfaces/state.py
    # и прокинуть его сюда (например, system.example_state).
    # Но для примера:
    # state = system.example_state

    # 2. Инициализируем Клиент (Отвечает за I/O, сессии, запросы)
    # client = MyClient(state=state, api_key=api_key)

    # 3. Инициализируем Воркер событий (Отвечает за фоновый поллинг)
    # events = MyEvents(client=client, event_bus=system.event_bus)

    # 4. Регистрируем Навыки (То, что LLM сможет вызывать)
    # register_instance(MySkills(client))

    # 5. Регистрируем Контекст (То, что LLM будет видеть на своей приборной панели)
    # system.context_registry.register_provider(
    #     name="example_interface",
    #     provider_func=client.get_context_block,
    #     section=ContextSection.INTERFACES,
    # )

    system_logger.info("[Example] Пользовательский интерфейс загружен.")

    # Обязательно возвращаем объекты, у которых есть async def start() и async def stop()
    # return [client, events]
    return []

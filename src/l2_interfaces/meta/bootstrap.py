"""
Инициализатор интерфейса самомодификации (Meta).

Отвечает за регистрацию навыков управления конфигурацией агента (динамическое изменение YAML).
В зависимости от уровня доступа (Access Level 0-3), ограничивает выдаваемые агенту возможности.
"""

from typing import List, Any, TYPE_CHECKING
from src.utils.logger import system_logger
from src.l2_interfaces.meta.client import MetaClient

from src.l2_interfaces.meta.skills.level_safe import MetaSafe
from src.l2_interfaces.meta.skills.level_configurator import MetaConfigurator
from src.l2_interfaces.meta.skills.level_architect import MetaArchitect
from src.l2_interfaces.meta.skills.level_creator import MetaCreator

from src.l3_agent.skills.custom import CustomSkillsRegistry
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_meta(system: "System") -> List[Any]:
    """
    Инициализирует интерфейс Meta.

    Args:
        system (System): Главный DI-контейнер фреймворка.

    Returns:
        List[Any]: Пустой список (Meta-интерфейс не требует фоновых поллеров).
    """
    settings_path = system.root_dir / "config" / "settings.yaml"
    interfaces_path = system.root_dir / "config" / "interfaces.yaml"

    meta_config = system.interfaces_config.meta

    client = MetaClient(
        agent_state=system.agent_state,
        event_bus=system.event_bus,
        settings_path=settings_path,
        interfaces_path=interfaces_path,
        access_level=meta_config.access_level,
        available_models=system.settings.llm.available_models,
        custom_skills_enabled=meta_config.custom_skills_enabled,
    )

    # L3 Registry для кастомных навыков
    custom_registry = CustomSkillsRegistry(system.local_data_dir)

    if meta_config.custom_skills_enabled:
        custom_registry.load_and_register_all()

    # Динамическая регистрация встроенных навыков согласно уровню доступа (RBAC)
    register_instance(MetaSafe(client))

    if meta_config.access_level >= 1:
        register_instance(MetaConfigurator(client, system.root_dir))

    if meta_config.access_level >= 2:
        register_instance(MetaArchitect(client))

    # Выдаем агенту "руки" для создания навыков только если тумблер включен
    if meta_config.access_level >= 3:
        if meta_config.custom_skills_enabled:
            register_instance(MetaCreator(client, custom_registry))
        else:
            system_logger.info(
                "[Meta] Access Level 3 (CREATOR) активен, но кастомные навыки отключены в settings.yaml."
            )

    system.context_registry.register_provider(
        name="meta", provider_func=client.get_context_block, section=ContextSection.INTERFACES
    )

    system_logger.info(
        f"[Meta] Интерфейс загружен (Access Level: {meta_config.access_level})."
    )
    return []

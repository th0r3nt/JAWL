"""
Self-modification interface plugin (Meta).

Managing agent configuration at runtime and custom skills.
"""

from typing import List, Any, Dict, Optional

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.meta.state import CustomDashboardState
from src.l2_interfaces.meta.client import MetaClient

from src.l2_interfaces.meta.skills.level_safe import MetaSafe
from src.l2_interfaces.meta.skills.level_configurator import MetaConfigurator
from src.l2_interfaces.meta.skills.level_architect import MetaArchitect
from src.l2_interfaces.meta.skills.level_creator import MetaCreator

from src.l3_agent.skills.custom import CustomSkillsRegistry
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class MetaPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "META"

    @property
    def description(self) -> str:
        return "Dynamic framework configuration and custom skills injection."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.meta.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        meta_config = container.interfaces_config.meta

        # Initialize dashboard state
        state = CustomDashboardState()
        container.l0_states["dashboard"] = state

        settings_path = container.root_dir / "config" / "settings.yaml"
        interfaces_path = container.root_dir / "config" / "interfaces.yaml"

        client = MetaClient(
            agent_state=container.agent_state,
            event_bus=container.event_bus,
            settings_path=settings_path,
            interfaces_path=interfaces_path,
            access_level=meta_config.access_level,
            available_models=container.settings.llm.available_models,
            custom_skills_enabled=meta_config.custom_skills_enabled,
        )

        custom_registry = CustomSkillsRegistry(container.local_data_dir)

        if meta_config.custom_skills_enabled:
            custom_registry.load_and_register_all()

        register_instance(MetaSafe(client))

        if meta_config.access_level >= 1:
            register_instance(MetaConfigurator(client, container.root_dir))

        if meta_config.access_level >= 2:
            register_instance(MetaArchitect(client))

        if meta_config.access_level >= 3:
            if meta_config.custom_skills_enabled:
                register_instance(MetaCreator(client, custom_registry))
            else:
                main_logger.info(
                    "[Meta] Access Level 3 (CREATOR) is active, but custom skills are disabled."
                )

        container.context_registry.register_provider(
            name=self.name.lower(),
            provider_func=client.get_context_block,
            section=ContextSection.INTERFACES,
        )

        main_logger.info(
            f"[Meta] Interface loaded (Access Level: {meta_config.access_level})."
        )
        return []

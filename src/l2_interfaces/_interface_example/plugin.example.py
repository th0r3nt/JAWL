"""
Plugin for the custom L2 interface.

This file is the entry point for your module. The framework will automatically find it (Plugin Discovery).
Dependency injection (DI) occurs here: we create the L0 State, configure the Client,
the Worker (Events), and register the Skills.

Developer Tips:
1. Do not write business logic here. The Plugin is only needed to "assemble" the constructor.
2. To allow enabling/disabling your plugin, you need to add its structure to
   Pydantic schemas in `src/utils/settings.py` (inside the InterfacesConfig class).
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l3_agent.skills.registry import register_instance  # noqa: F401
from src.l3_agent.context.registry import ContextSection  # noqa: F401
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig

# In real code, import your modules:
# from src.l2_interfaces.my_module.state import MyState
# from src.l2_interfaces.my_module.client import MyClient
# from src.l2_interfaces.my_module.events import MyEvents
# from src.l2_interfaces.my_module.skills.tools import MySkills


class ExamplePlugin(BaseInterface):
    """
    Main plugin class. Inherits from BaseInterface, which guarantees
    the presence of necessary properties and methods for the initializer.
    """

    @property
    def name(self) -> str:
        return "EXAMPLE INTERFACE"

    @property
    def description(self) -> str:
        return "Test description for the agent."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        # In reality, there will be something like: return config.my_module.enabled
        return False

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        """
        Initializes the interface and integrates it into the JAWL core.

        Args:
            container: Framework DI container (provides access to databases, event bus).
            env_vars: Dictionary of secrets (read from .env).

        Returns:
            List[Any]: List of lifecycle components (usually client and events)
                       on which the orchestrator will call .start() and .stop() methods.
        """

        # 0. Extract keys
        # api_key = env_vars.get("MY_API_KEY")
        # if not api_key:
        #     main_logger.error(f"[{self.name}] API Key not found. Disabled.")
        #     self.register_off_provider(container.context_registry)
        #     return []

        # 1. Create state (dashboard) and save it to the container
        # state = MyState()
        # container.l0_states["example"] = state

        # 2. Initialize Client (handles I/O, sessions, requests)
        # client = MyClient(state=state, api_key=api_key)

        # 3. Initialize Event Worker (handles background polling)
        # events = MyEvents(client=client, event_bus=container.event_bus)

        # 4. Register Skills (tools the LLM can call)
        # register_instance(MySkills(client))

        # 5. Register Context (what the LLM will see on its dashboard)
        # container.context_registry.register_provider(
        #     name=self.name.lower().replace(" ", "_"),
        #     provider_func=client.get_context_block,
        #     section=ContextSection.INTERFACES,
        # )

        main_logger.info(f"[{self.name}] Custom interface loaded.")

        # Must return objects that have async def start() and async def stop()
        # return [client, events]
        return []

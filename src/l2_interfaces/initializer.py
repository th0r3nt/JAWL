"""
Main initializer of the interface layer (L2).

Scans the directory for plugins (Discovery pattern), initializes them,
and gathers lifecycle components. For non-migrated interfaces,
a temporary Legacy mechanism is supported.
"""

import os
import importlib.util
import inspect
from pathlib import Path
from typing import List, Any, Dict, Optional, TYPE_CHECKING

from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface

if TYPE_CHECKING:
    from src.system.container import SystemContainer


def initialize_l2_interfaces(
    container: "SystemContainer", env_vars: Dict[str, Optional[str]]
) -> List[Any]:
    """
    Orchestrates the launch of L2 interfaces.
    1. Finds and loads new plugins (plugin.py).
    2. Performs Legacy initialization for older interfaces.

    Args:
        container: Main system DI container.
        env_vars: Dictionary of secret tokens from the .env file.

    Returns:
        List of initialized components for the Event Loop.
    """

    components: List[Any] = []
    config = container.interfaces_config

    # ================================================================
    # PLUGIN DISCOVERY SYSTEM
    # Walks through nested folders of src/l2_interfaces/
    # to find plugin.py

    interfaces_dir = Path(__file__).resolve().parent
    src_dir = interfaces_dir.parent.parent  # Path to JAWL root folder

    # Find all plugin.py files in the l2_interfaces folder
    for plugin_path in interfaces_dir.rglob("plugin.py"):
        # Calculate the correct module name (e.g., src.l2_interfaces.web.http.plugin)
        rel_path = plugin_path.relative_to(src_dir)
        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)

                # ==================================================================
                # Search for classes inherited from BaseInterface

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseInterface) and obj is not BaseInterface:
                        plugin_instance = obj()

                        if plugin_instance.is_enabled(config):
                            main_logger.debug(
                                f"[Discovery] Initializing plugin {plugin_instance.name}."
                            )
                            lifecycle_comps = plugin_instance.setup(container, env_vars)
                            components.extend(lifecycle_comps)
                        else:
                            plugin_instance.register_off_provider(container.context_registry)

            except Exception as e:
                main_logger.error(f"[Discovery] Error loading plugin {plugin_path}: {e}")

    # Returns all components that will later be started in SystemOrchestrator
    return components

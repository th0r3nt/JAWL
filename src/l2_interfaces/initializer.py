"""
Главный инициализатор слоя интерфейсов (L2).

Сканирует директорию на наличие плагинов (паттерн Discovery), инициализирует их
и собирает компоненты жизненного цикла. Для немигрированных интерфейсов
поддерживается временный Legacy-механизм.
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
    Оркестрирует запуск L2 интерфейсов.
    1. Находит и загружает новые плагины (plugin.py).
    2. Выполняет Legacy инициализацию для старых интерфейсов.

    Args:
        container: Главный DI-контейнер системы.
        env_vars: Словарь с секретными токенами из .env файла.

    Returns:
        Список инициализированных компонентов для Event Loop.
    """

    components: List[Any] = []
    config = container.interfaces_config

    # ================================================================
    # PLUGIN DISCOVERY SYSTEM
    # Проходится по вложенным папкам src/l2_interfaces/,
    # чтобы найти plugin.py

    interfaces_dir = Path(__file__).resolve().parent
    src_dir = interfaces_dir.parent.parent  # Путь до корневой папки JAWL

    # Ищем все файлы plugin.py в папке l2_interfaces
    for plugin_path in interfaces_dir.rglob("plugin.py"):
        # Вычисляем корректное имя модуля (например, src.l2_interfaces.web.http.plugin)
        rel_path = plugin_path.relative_to(src_dir)
        module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)

                # ==================================================================
                # Поиск классов, унаследованных от BaseInterface

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseInterface) and obj is not BaseInterface:
                        plugin_instance = obj()

                        if plugin_instance.is_enabled(config):
                            main_logger.debug(
                                f"[Discovery] Инициализация плагина {plugin_instance.name}."
                            )
                            lifecycle_comps = plugin_instance.setup(container, env_vars)
                            components.extend(lifecycle_comps)
                        else:
                            plugin_instance.register_off_provider(container.context_registry)

            except Exception as e:
                main_logger.error(
                    f"[Discovery] Ошибка при загрузке плагина {plugin_path}: {e}"
                )

    # Возвращает все компоненты, которые после будут запущены в SystemOrchestrator
    return components

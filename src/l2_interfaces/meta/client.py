"""
Клиент Meta-интерфейса.

Обеспечивает агенту механизм рефлексии и возможность изменять собственную
YAML-конфигурацию в рантайме (без прямого редактирования файлов хост-системы оператором).
"""

import os
from pathlib import Path
from typing import Any, List
from ruamel.yaml import YAML

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.logger import system_logger


class MetaClient:
    """Менеджер самомодификации настроек JAWL."""

    def __init__(
        self,
        agent_state: AgentState,
        event_bus: EventBus,
        settings_path: Path,
        interfaces_path: Path,
        access_level: int,
        available_models: List[str],
        custom_skills_enabled: bool,
    ) -> None:
        """
        Инициализирует мета-клиент.

        Args:
            agent_state: Состояние агента.
            event_bus: Шина событий (для рассылки апдейтов конфига).
            settings_path: Путь к settings.yaml.
            interfaces_path: Путь к interfaces.yaml.
            access_level: Уровень мета-доступа (0 - SAFE, ..., 3 - CREATOR).
            available_models: Список разрешенных LLM.
            custom_skills_enabled: Разрешено ли создавать кастомные навыки.
        """
        self.agent_state = agent_state
        self.bus = event_bus
        self.settings_path = settings_path
        self.interfaces_path = interfaces_path
        self.access_level = access_level
        self.available_models = available_models
        self.custom_skills_enabled = custom_skills_enabled

        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    async def update_yaml(self, file_path: Path, path_keys: List[str], new_value: Any) -> bool:
        """
        Универсальный метод для глубокого обновления YAML файлов (settings или interfaces).

        Args:
            file_path: Какой файл менять.
            path_keys: Путь по вложенным ключам (например: ["llm", "temperature"]).
            new_value: Новое значение.

        Returns:
            True, если сохранено успешно, иначе False.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = self.yaml.load(f)

            target = data
            for key in path_keys[:-1]:
                if key not in target:
                    target[key] = {}
                target = target[key]

            target[path_keys[-1]] = new_value

            with open(file_path, "w", encoding="utf-8") as f:
                self.yaml.dump(data, f)

            return True
        except Exception as e:
            system_logger.error(f"[Meta] Ошибка обновления {file_path.name}: {e}")
            return False

    def has_env_key(self, key_name: str) -> bool:
        """Проверяет наличие токена в переменных окружения (например 'GITHUB_TOKEN')."""
        return bool(os.getenv(key_name, "").strip())

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Провайдер контекста для ContextRegistry.
        Отдает агенту список его мета-возможностей и текущий Access Level.
        """
        
        access_levels_desc = (
            "Существующие уровни доступа: \n"
            "- 0/SAFE: Базовые настройки.\n"
            "- 1/CONFIGURATOR: Управление памятью и продвинутые настройки конфигурации.\n"
            "- 2/ARCHITECT: Управление системой и интерфейсами.\n"
            "- 3/CREATOR: Регистрация кастомных скриптов как нативных навыков."
        )

        models_str = (
            ", ".join(self.available_models) if self.available_models else "Список пуст"
        )

        custom_status = "отключены"
        if self.custom_skills_enabled:
            custom_status = "включены (требуется 3/CREATOR)"

        return (
            f"### META [ON]\n"
            f"* Access Level: {self.access_level} (текущий уровень) \n{access_levels_desc}\n"
            f"* Custom Skills: {custom_status}\n"
            f"* Available LLM models: [{models_str}]"
        )

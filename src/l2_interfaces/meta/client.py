import os
from pathlib import Path
from ruamel.yaml import YAML

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.logger import system_logger


class MetaClient:
    def __init__(
        self,
        agent_state: AgentState,
        event_bus: EventBus,
        settings_path: Path,
        interfaces_path: Path,
        access_level: int,
        available_models: list[str],
        custom_skills_enabled: bool,
    ):
        self.agent_state = agent_state
        self.bus = event_bus
        self.settings_path = settings_path
        self.interfaces_path = interfaces_path
        self.access_level = access_level
        self.available_models = available_models
        self.custom_skills_enabled = custom_skills_enabled

        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    async def update_yaml(self, file_path: Path, path_keys: list[str], new_value) -> bool:
        """Универсальный метод для обновления YAML файлов (settings или interfaces)."""
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
        """Проверяет наличие токена в переменных окружения."""
        return bool(os.getenv(key_name, "").strip())

    async def get_context_block(self, **kwargs) -> str:
        """
        Провайдер контекста для ContextRegistry.
        """

        access_levels_desc = (
            "  - 0/SAFE: Базовые настройки.\n"
            "  - 1/CONFIGURATOR: Управление памятью и продвинутые настройки конфигурации.\n"
            "  - 2/ARCHITECT: Управление системой и интерфейсами.\n"
            "  - 3/CREATOR: Регистрация кастомных скриптов как нативных навыков."
        )

        models_str = (
            ", ".join(self.available_models) if self.available_models else "Список пуст"
        )

        custom_status = "отключены"
        if self.custom_skills_enabled:
            custom_status = "включены (требуется 3/CREATOR)"

        return (
            f"### META [ON]\n"
            f"* Access Level: {self.access_level} / 3\n{access_levels_desc}\n"
            f"* Custom Skills: {custom_status}\n"
            f"* Available LLM models: [{models_str}]"
        )

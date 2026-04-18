from pathlib import Path
from ruamel.yaml import YAML

from src.l0_state.agent.state import AgentState
from src.utils.event.bus import EventBus
from src.utils.logger import system_logger


class MetaClient:
    def __init__(self, agent_state: AgentState, event_bus: EventBus, settings_path: Path):
        self.agent_state = agent_state
        self.bus = event_bus
        self.settings_path = settings_path

        # ruamel.yaml сохраняет структуру и все комментарии (#) в файле
        self.yaml = YAML()
        self.yaml.preserve_quotes = True

    async def update_setting(self, path_keys: list[str], new_value, log_msg: str) -> bool:
        """
        Универсальный метод для обновления settings.yaml.
        path_keys - путь до ключа (например, ["system", "heartbeat_interval"])
        """
        try:
            with open(self.settings_path, "r", encoding="utf-8") as f:
                data = self.yaml.load(f)

            # Идем вглубь словаря по ключам
            target = data
            for key in path_keys[:-1]:
                target = target[key]

            target[path_keys[-1]] = new_value

            with open(self.settings_path, "w", encoding="utf-8") as f:
                self.yaml.dump(data, f)

            system_logger.info(f"[Meta] {log_msg}")
            return True
        except Exception as e:
            system_logger.error(f"[Meta] Ошибка обновления settings.yaml: {e}")
            return False

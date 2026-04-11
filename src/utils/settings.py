import yaml
from pathlib import Path
from pydantic import BaseModel


# ==========================================
# Модели для interfaces.yaml
# ==========================================


class HostOSConfig(BaseModel):
    enabled: bool = True
    madness_level: int = 1
    env_access: bool = False
    monitoring_interval_sec: int = 30
    execution_timeout_sec: int = 60
    file_read_max_lines: int = 5000
    file_list_limit: int = 100
    http_response_max_chars: int = 5000
    top_processes_limit: int = 10


class HostTerminalConfig(BaseModel):
    enabled: bool = True


class HostConfig(BaseModel):
    os: HostOSConfig
    terminal: HostTerminalConfig


class TelethonConfig(BaseModel):
    enabled: bool = False
    session_name: str = "agent_telethon"


class AiogramConfig(BaseModel):
    enabled: bool = False


class TelegramConfig(BaseModel):
    telethon: TelethonConfig
    aiogram: AiogramConfig


class InterfacesConfig(BaseModel):
    host: HostConfig
    telegram: TelegramConfig


# ==========================================
# Модели для settings.yaml
# ==========================================


class IdentityConfig(BaseModel):
    agent_name: str = "E.X.E."


class LLMConfig(BaseModel):
    model_name: str = "gemini-1.5-pro"
    temperature: float = 0.7
    max_react_steps: int = 15


class VectorDBConfig(BaseModel):
    similarity_threshold: float = 0.43
    embedding_model: str = "intfloat/multilingual-e5-small"
    vector_size: int = 384


class ContextDepthConfig(BaseModel):
    ticks: int = 20
    tick_result_max_chars: int = 10000  # Лимит на размер результата тулза в контексте


class SystemConfig(BaseModel):
    vector_db: VectorDBConfig
    tick_interval_sec: int = 10
    context_depth: ContextDepthConfig


class SettingsConfig(BaseModel):
    identity: IdentityConfig
    llm: LLMConfig
    system: SystemConfig


# ==========================================
# Загрузчик
# ==========================================


def load_yaml(file_path: Path) -> dict:
    if not file_path.exists():
        raise FileNotFoundError(f"Конфигурационный файл не найден: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config() -> tuple[SettingsConfig, InterfacesConfig]:
    """Загружает и валидирует настройки из YAML файлов."""
    base_dir = Path.cwd() / "config"

    settings_data = load_yaml(base_dir / "settings.yaml")
    interfaces_data = load_yaml(base_dir / "interfaces.yaml")

    return SettingsConfig(**settings_data), InterfacesConfig(**interfaces_data)

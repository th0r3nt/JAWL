import yaml
from pathlib import Path
from pydantic import BaseModel


# ==========================================
# Модели для interfaces.yaml
# ==========================================


class HostOSConfig(BaseModel):
    enabled: bool
    madness_level: int
    env_access: bool
    monitoring_interval_sec: int
    execution_timeout_sec: int
    file_read_max_chars: int
    file_list_limit: int
    http_response_max_chars: int
    top_processes_limit: int


class HostConfig(BaseModel):
    os: HostOSConfig


class TelethonConfig(BaseModel):
    enabled: bool
    session_name: str


class AiogramConfig(BaseModel):
    enabled: bool


class TelegramConfig(BaseModel):
    telethon: TelethonConfig
    aiogram: AiogramConfig


class WebConfig(BaseModel):
    enabled: bool
    request_timeout_sec: int
    max_page_chars: int


class MetaConfig(BaseModel):
    enabled: bool


class InterfacesConfig(BaseModel):
    host: HostConfig
    telegram: TelegramConfig
    web: WebConfig
    meta: MetaConfig


# ==========================================
# Модели для settings.yaml
# ==========================================


class IdentityConfig(BaseModel):
    agent_name: str


class LLMConfig(BaseModel):
    model_name: str
    temperature: float
    max_react_steps: int


class VectorDBConfig(BaseModel):
    similarity_threshold: float
    embedding_model: str
    vector_size: int
    auto_rag_top_k: int


class ContextDepthConfig(BaseModel):
    ticks: int
    tick_result_max_chars: int  # Лимит на размер результата тулза в контексте


class EventAccelerationConfig(BaseModel):
    critical_multiplier: float
    high_multiplier: float
    medium_multiplier: float
    low_multiplier: float
    background_multiplier: float


class SystemConfig(BaseModel):
    timezone: int
    vector_db: VectorDBConfig
    heartbeat_interval: int
    continuous_cycle: bool
    event_acceleration: EventAccelerationConfig
    context_depth: ContextDepthConfig
    max_mental_state_entities: int


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

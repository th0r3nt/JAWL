import yaml
from pathlib import Path
from pydantic import BaseModel


# ==========================================
# Модели для interfaces.yaml
# ==========================================


class HostOSConfig(BaseModel):
    enabled: bool
    access_level: int
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


class WebSearchConfig(BaseModel):
    enabled: bool
    request_timeout_sec: int
    max_page_chars: int


class WebConfig(BaseModel):
    search: WebSearchConfig


class MetaConfig(BaseModel):
    enabled: bool


class MultimodalityConfig(BaseModel):
    enabled: bool


class InterfacesConfig(BaseModel):
    host: HostConfig
    telegram: TelegramConfig
    web: WebConfig
    meta: MetaConfig
    multimodality: MultimodalityConfig


# ==========================================
# Модели для settings.yaml
# ==========================================


class IdentityConfig(BaseModel):
    agent_name: str


class LLMConfig(BaseModel):
    model_name: str
    is_multimodal: bool = False
    temperature: float
    max_react_steps: int


class VectorDBConfig(BaseModel):
    similarity_threshold: float
    embedding_model: str
    vector_size: int
    auto_rag_top_k: int


class ContextDepthConfig(BaseModel):
    ticks: int
    detailed_ticks: int
    tick_action_max_chars: int
    tick_result_max_chars: int


class EventAccelerationConfig(BaseModel):
    critical_multiplier: float
    high_multiplier: float
    medium_multiplier: float
    low_multiplier: float
    background_multiplier: float


class TasksConfig(BaseModel):
    enabled: bool
    max_tasks: int 


class PersonalityTraitsConfig(BaseModel):
    enabled: bool
    max_traits: int


class MentalStatesConfig(BaseModel):
    enabled: bool
    max_entities: int


class DrivesConfig(BaseModel):
    enabled: bool
    default_decay_rate_per_hour: float
    max_reflections_history: int
    max_custom_drives: int


class SQLConfig(BaseModel):
    tasks: TasksConfig
    personality_traits: PersonalityTraitsConfig
    mental_states: MentalStatesConfig
    drives: DrivesConfig


class SystemConfig(BaseModel):
    timezone: int
    vector_db: VectorDBConfig
    heartbeat_interval: int
    continuous_cycle: bool
    event_acceleration: EventAccelerationConfig
    context_depth: ContextDepthConfig

    sql: SQLConfig


class SettingsConfig(BaseModel):
    identity: IdentityConfig
    llm: LLMConfig
    system: SystemConfig


# ==========================================
# Загрузчик
# ==========================================


def load_yaml(file_path: Path) -> dict:
    """Безопасно читает YAML файл и возвращает словарь."""

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

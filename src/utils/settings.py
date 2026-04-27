import shutil
import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict
from yaml.constructor import ConstructorError

# ==========================================
# Модели для interfaces.yaml
# ==========================================


class HostOSConfig(BaseModel):
    enabled: bool
    desktop_interactions: bool = False

    access_level: int
    env_access: bool
    framework_tree_depth: int = 1
    monitoring_interval_sec: int
    execution_timeout_sec: int
    file_read_max_chars: int
    file_list_limit: int
    http_response_max_chars: int
    top_processes_limit: int
    file_diff_max_chars: int = 300

    workspace_max_opened_files: int = 3
    recent_file_changes_limit: int = 5


class HostConfig(BaseModel):
    os: HostOSConfig


class TelethonConfig(BaseModel):
    enabled: bool
    session_name: str
    recent_chats_limit: int = 15
    private_chat_history_limit: int = 3
    incoming_history_limit: int = 5
    # TODO: добавить больше параметров для изменения


class AiogramConfig(BaseModel):
    enabled: bool
    recent_chats_limit: int = 15


class TelegramConfig(BaseModel):
    telethon: TelethonConfig
    aiogram: AiogramConfig


class GithubConfig(BaseModel):
    enabled: bool
    agent_account: bool
    request_timeout_sec: int
    history_limit: int
    polling_interval_sec: int = 300


class EmailConfig(BaseModel):
    enabled: bool
    polling_interval_sec: int = 60
    recent_limit: int = 10


class DeepResearchConfig(BaseModel):
    max_queries: int
    max_results_per_query: int
    max_pages_to_read: int
    total_max_chars: int


class WebSearchConfig(BaseModel):
    enabled: bool
    request_timeout_sec: int
    max_page_chars: int
    deep_research: DeepResearchConfig


class WebConfig(BaseModel):
    search: WebSearchConfig


class MetaConfig(BaseModel):
    enabled: bool
    access_level: int = 0  # 0: SAFE, 1: CONFIGURATOR, 2: ARCHITECT


class MultimodalityConfig(BaseModel):
    enabled: bool


class CalendarConfig(BaseModel):
    enabled: bool
    polling_interval_sec: int
    upcoming_events_limit: int


class InterfacesConfig(BaseModel):
    host: HostConfig
    telegram: TelegramConfig
    github: GithubConfig
    web: WebConfig
    meta: MetaConfig
    multimodality: MultimodalityConfig
    calendar: CalendarConfig
    email: EmailConfig


# ==========================================
# Модели для settings.yaml
# ==========================================


class IdentityConfig(BaseModel):
    agent_name: str


class LLMConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str
    available_models: list[str] = []
    is_multimodal: bool = False
    temperature: float
    max_react_steps: int


class VectorDBConfig(BaseModel):
    similarity_threshold: float
    embedding_model: str
    vector_size: int
    auto_rag_top_k: int
    auto_rag_max_query_chars: int


class ContextDepthConfig(BaseModel):
    ticks: int
    detailed_ticks: int
    tick_action_max_chars: int
    tick_result_max_chars: int
    tick_thoughts_short_max_chars: int
    tick_action_short_max_chars: int
    tick_result_short_max_chars: int


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
    decay_rate: float
    decay_interval_sec: int
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


class UniqueKeyLoader(yaml.SafeLoader):
    """Кастомный загрузчик YAML, который падает с ошибкой при дублировании ключей."""

    pass


def construct_mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ConstructorError(
                None,
                None,
                f"Обнаружен дубликат ключа '{key}' в YAML файле. Исправьте конфигурацию.",
                key_node.start_mark,
            )
        value = loader.construct_object(value_node, deep=deep)
        mapping[key] = value
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, construct_mapping
)


def load_yaml(file_path: Path) -> dict:
    """Безопасно читает YAML файл и возвращает словарь с автофикс-кодировкой."""
    if not file_path.exists():
        raise FileNotFoundError(f"Конфигурационный файл не найден: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            # Заменяем yaml.safe_load на yaml.load с строгим парсером
            return yaml.load(f, Loader=UniqueKeyLoader) or {}
    except UnicodeDecodeError:
        # Лечим сломанную кодировку
        with open(file_path, "r", encoding="cp1251") as f:
            return yaml.load(f, Loader=UniqueKeyLoader) or {}


def load_config() -> tuple[SettingsConfig, InterfacesConfig]:
    """Загружает и валидирует настройки из YAML файлов. Автовосстанавливает при отсутствии."""

    base_dir = Path.cwd() / "config"

    settings_file = base_dir / "settings.yaml"
    settings_example = base_dir / "settings.example.yaml"

    interfaces_file = base_dir / "interfaces.yaml"
    interfaces_example = base_dir / "interfaces.example.yaml"

    # Автовосстановление файлов конфигурации из .example
    if not settings_file.exists() and settings_example.exists():
        shutil.copy(settings_example, settings_file)

    if not interfaces_file.exists() and interfaces_example.exists():
        shutil.copy(interfaces_example, interfaces_file)

    settings_data = load_yaml(settings_file)
    interfaces_data = load_yaml(interfaces_file)

    return SettingsConfig(**settings_data), InterfacesConfig(**interfaces_data)

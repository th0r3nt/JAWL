# Файл: src/utils/settings.py
import shutil
import yaml
from pathlib import Path
from pydantic import BaseModel, ConfigDict, Field
from yaml.constructor import ConstructorError

from src.utils.logger import system_logger

# ==========================================
# Модели для interfaces.yaml
# ==========================================


class HostOSConfig(BaseModel):
    enabled: bool = False
    desktop_interactions: bool = False

    access_level: int = 0
    env_access: bool = False

    require_deploy_sessions: bool = True
    deploy_max_retries: int = 5

    framework_tree_depth: int = 1

    monitoring_interval_sec: int = 30
    execution_timeout_sec: int = 60
    file_read_max_chars: int = 10000
    file_list_limit: int = 100
    top_processes_limit: int = 10
    file_diff_max_chars: int = 300

    workspace_max_opened_files: int = 10
    recent_file_changes_limit: int = 5
    workspace_max_file_chars: int = 10000


class HostTerminalConfig(BaseModel):
    enabled: bool = True
    history_limit: int = 50
    context_limit: int = 10


class HostConfig(BaseModel):
    os: HostOSConfig = Field(default_factory=HostOSConfig)
    terminal: HostTerminalConfig = Field(default_factory=HostTerminalConfig)


class TelethonConfig(BaseModel):
    enabled: bool = False
    session_name: str = "agent_telethon"
    recent_chats_limit: int = 20
    private_chat_history_limit: int = 3
    incoming_history_limit: int = 8


class AiogramConfig(BaseModel):
    enabled: bool = False
    recent_chats_limit: int = 20


class TelegramConfig(BaseModel):
    telethon: TelethonConfig = Field(default_factory=TelethonConfig)
    aiogram: AiogramConfig = Field(default_factory=AiogramConfig)


class GithubConfig(BaseModel):
    enabled: bool = False
    agent_account: bool = False
    request_timeout_sec: int = 15
    history_limit: int = 10
    polling_interval_sec: int = 180


class EmailConfig(BaseModel):
    enabled: bool = False
    polling_interval_sec: int = 60
    recent_limit: int = 5


class DeepResearchConfig(BaseModel):
    max_queries: int = 10
    max_results_per_query: int = 5
    max_pages_to_read: int = 15
    total_max_chars: int = 30000


class WebSearchConfig(BaseModel):
    enabled: bool = True
    search_engine: str = "duckduckgo"
    reader_engine: str = "jina"
    request_timeout_sec: int = 15
    max_page_chars: int = 10000
    deep_research: DeepResearchConfig = Field(default_factory=DeepResearchConfig)


class WebHTTPConfig(BaseModel):
    enabled: bool = True
    request_timeout_sec: int = 15
    max_response_chars: int = 10000


class WebBrowserConfig(BaseModel):
    enabled: bool = False
    headless: bool = True  # Показывать ли графическое окно (False полезно для отладки)
    timeout_sec: int = 30  # Таймаут на загрузку страниц
    idle_timeout_sec: int = (
        900  # 15 минут простоя перед авто-закрытием браузера для очистки ОЗУ
    )


class WebConfig(BaseModel):
    search: WebSearchConfig = Field(default_factory=WebSearchConfig)
    http: WebHTTPConfig = Field(default_factory=WebHTTPConfig)
    browser: WebBrowserConfig = Field(default_factory=WebBrowserConfig)


class MetaConfig(BaseModel):
    enabled: bool = False
    access_level: int = 0  # 0: SAFE, 1: CONFIGURATOR, 2: ARCHITECT, 3: CREATOR
    custom_skills_enabled: bool = True


class MultimodalityConfig(BaseModel):
    enabled: bool = False


class CalendarConfig(BaseModel):
    enabled: bool = True
    polling_interval_sec: int = 60
    upcoming_events_limit: int = 10


class InterfacesConfig(BaseModel):
    host: HostConfig = Field(default_factory=HostConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    github: GithubConfig = Field(default_factory=GithubConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    meta: MetaConfig = Field(default_factory=MetaConfig)
    multimodality: MultimodalityConfig = Field(default_factory=MultimodalityConfig)
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    email: EmailConfig = Field(default_factory=EmailConfig)


# ==========================================
# Модели для settings.yaml
# ==========================================


class IdentityConfig(BaseModel):
    agent_name: str = "Agent"


class LLMConfig(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    model: str = "unknown"
    available_models: list[str] = Field(default_factory=list)
    is_multimodal: bool = False
    temperature: float = 1.0
    max_react_steps: int = 15


class LoggingConfig(BaseModel):
    max_file_size_mb: float = 5.0
    backup_count: int = 1


class VectorDBConfig(BaseModel):
    similarity_threshold: float = 0.65
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    vector_size: int = 384
    auto_rag_top_k: int = 1
    auto_rag_max_query_chars: int = 200


class ContextDepthConfig(BaseModel):
    ticks: int = 15
    detailed_ticks: int = 3
    tick_action_max_chars: int = 10000
    tick_result_max_chars: int = 20000
    tick_thoughts_short_max_chars: int = 1000
    tick_action_short_max_chars: int = 100
    tick_result_short_max_chars: int = 500


class EventAccelerationConfig(BaseModel):
    critical_multiplier: float = 0.0
    high_multiplier: float = 0.2
    medium_multiplier: float = 0.6
    low_multiplier: float = 0.7
    background_multiplier: float = 0.8


class TasksConfig(BaseModel):
    enabled: bool = True
    max_tasks: int = 10


class PersonalityTraitsConfig(BaseModel):
    enabled: bool = True
    max_traits: int = 10


class MentalStatesConfig(BaseModel):
    enabled: bool = True
    max_entities: int = 10


class DrivesConfig(BaseModel):
    enabled: bool = True
    decay_rate: float = 10.0
    decay_interval_sec: int = 900
    max_reflections_history: int = 4
    max_custom_drives: int = 5


class SQLConfig(BaseModel):
    tasks: TasksConfig = Field(default_factory=TasksConfig)
    personality_traits: PersonalityTraitsConfig = Field(
        default_factory=PersonalityTraitsConfig
    )
    mental_states: MentalStatesConfig = Field(default_factory=MentalStatesConfig)
    drives: DrivesConfig = Field(default_factory=DrivesConfig)


class SystemConfig(BaseModel):
    timezone: int = 0
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    vector_db: VectorDBConfig = Field(default_factory=VectorDBConfig)
    heartbeat_interval: int = 300
    continuous_cycle: bool = False
    proactive_guidance: bool = False
    event_acceleration: EventAccelerationConfig = Field(
        default_factory=EventAccelerationConfig
    )
    context_depth: ContextDepthConfig = Field(default_factory=ContextDepthConfig)

    sql: SQLConfig = Field(default_factory=SQLConfig)


class SettingsConfig(BaseModel):
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    system: SystemConfig = Field(default_factory=SystemConfig)


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
        with open(file_path, "r", encoding="utf-8-sig") as f:
            return yaml.load(f, Loader=UniqueKeyLoader) or {}
    except UnicodeDecodeError:
        with open(file_path, "r", encoding="cp1251") as f:
            return yaml.load(f, Loader=UniqueKeyLoader) or {}


def _log_missing_defaults(model: BaseModel, prefix: str = "", file_name: str = ""):
    """
    Рекурсивно проверяет, какие поля были установлены по дефолту (не переданы юзером),
    и выводит аккуратное предупреждение в лог.
    """
    # model_fields_set содержит только те ключи, которые были явно переданы при валидации
    missing_keys = set(model.model_fields.keys()) - model.model_fields_set

    if missing_keys:
        keys_str = ", ".join(f"'{prefix}{k}'" for k in missing_keys)
        system_logger.debug(
            f"[{file_name}] Отсутствуют настройки {keys_str}. Применены значения по умолчанию."
        )

    # Идем вглубь по вложенным моделям
    for key, value in model.__dict__.items():
        if isinstance(value, BaseModel):
            _log_missing_defaults(value, prefix=f"{prefix}{key}.", file_name=file_name)


def load_config() -> tuple[SettingsConfig, InterfacesConfig]:
    """
    Загружает и валидирует настройки из YAML файлов.
    Автовосстанавливает при отсутствии.
    """

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

    settings_config = SettingsConfig(**settings_data)
    interfaces_config = InterfacesConfig(**interfaces_data)

    # Логируем, если юзер не обновил файлы конфигурации и мы подставили дефолты
    _log_missing_defaults(settings_config, file_name="settings.yaml")
    _log_missing_defaults(interfaces_config, file_name="interfaces.yaml")

    return settings_config, interfaces_config

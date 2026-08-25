# -*- coding: utf-8 -*-
"""
Карта полей консоли ↔ ключей конфигурации.

Единственное место, где описано соответствие. Ключ словаря совпадает с
атрибутом `data-cfg` в разметке, так что фронтенд и бэкенд не могут разъехаться.

Формат ключа: `<источник>:<путь>`
  settings:llm.temperature   — config/settings.yaml
  env:LLM_API_URL            — .env

Списки вынесены отдельно: у них другая семантика записи (переписываются целиком).

ИНТЕГРИРОВАНО: «Параметры → Личность и LLM».
Остальные вкладки пока работают на значениях из разметки — по мере подключения
их поля добавляются сюда, и они автоматически начинают читаться и писаться.
"""

from __future__ import annotations

from typing import Dict, List

# ---------------------------------------------------------------- одиночные поля

# «Личность»
IDENTITY: Dict[str, str] = {
    "settings:identity.agent_name": "identity.agent_name",
    "settings:llm.language": "llm.language",
    "settings:system.proactive_guidance": "system.proactive_guidance",
}

# «Языковая модель»
LLM: Dict[str, str] = {
    "settings:llm.main_model": "llm.main_model",
    "settings:llm.temperature": "llm.temperature",
    "settings:llm.min_call_interval_sec": "llm.min_call_interval_sec",
    "settings:llm.max_react_steps": "llm.max_react_steps",
    "settings:llm.is_multimodal": "llm.is_multimodal",
}

# Роли моделей живут на других вкладках, но бейджи ролей показывает
# карточка «Доступные модели» — без них она врала бы.
MODEL_ROLES: Dict[str, str] = {
    "settings:system.swarm.subagent_model": "system.swarm.subagent_model",
    "settings:system.tree_of_thoughts.llm_model": "system.tree_of_thoughts.llm_model",
    "settings:system.subconscious.llm_model": "system.subconscious.llm_model",
}

# «Такт и события»
HEARTBEAT: Dict[str, str] = {
    "settings:system.continuous_cycle": "system.continuous_cycle",
    "settings:system.heartbeat_interval": "system.heartbeat_interval",
    "settings:system.timezone": "system.timezone",
    "settings:system.event_acceleration.critical_multiplier": "system.event_acceleration.critical_multiplier",
    "settings:system.event_acceleration.high_multiplier": "system.event_acceleration.high_multiplier",
    "settings:system.event_acceleration.medium_multiplier": "system.event_acceleration.medium_multiplier",
    "settings:system.event_acceleration.low_multiplier": "system.event_acceleration.low_multiplier",
    "settings:system.event_acceleration.background_multiplier": "system.event_acceleration.background_multiplier",
}

# «Контекст и RAG»
CONTEXT: Dict[str, str] = {
    "settings:system.context_depth.high_ticks": "system.context_depth.high_ticks",
    "settings:system.context_depth.medium_ticks": "system.context_depth.medium_ticks",
    "settings:system.context_depth.low_ticks": "system.context_depth.low_ticks",
    "settings:system.context_depth.tick_action_max_chars": "system.context_depth.tick_action_max_chars",
    "settings:system.context_depth.tick_result_max_chars": "system.context_depth.tick_result_max_chars",
    "settings:system.context_depth.tick_thoughts_short_max_chars": "system.context_depth.tick_thoughts_short_max_chars",
    "settings:system.context_depth.rag.enabled": "system.context_depth.rag.enabled",
    "settings:system.context_depth.rag.depth_limit": "system.context_depth.rag.depth_limit",
    "settings:system.context_depth.rag.max_vector_blocks": "system.context_depth.rag.max_vector_blocks",
    "settings:system.context_depth.rag.max_graph_nodes": "system.context_depth.rag.max_graph_nodes",
    "settings:system.context_depth.rag.max_query_chars": "system.context_depth.rag.max_query_chars",
}

# «Память»
MEMORY: Dict[str, str] = {
    "settings:system.db.vector.embedding_model": "system.db.vector.embedding_model",
    "settings:system.db.vector.vector_size": "system.db.vector.vector_size",
    "settings:system.db.vector.similarity_threshold": "system.db.vector.similarity_threshold",
    "settings:system.db.graph.max_nodes": "system.db.graph.max_nodes",
    "settings:system.db.graph.max_edges_per_node": "system.db.graph.max_edges_per_node",
    "settings:system.db.sql.tasks.max_tasks": "system.db.sql.tasks.max_tasks",
    "settings:system.db.sql.notes.max_notes": "system.db.sql.notes.max_notes",
    "settings:system.db.sql.personality_traits.max_traits": "system.db.sql.personality_traits.max_traits",
    "settings:system.db.sql.mental_states.max_entities": "system.db.sql.mental_states.max_entities",
    "settings:system.db.sql.hypotheses.enabled": "system.db.sql.hypotheses.enabled",
    "settings:system.db.sql.hypotheses.max_clusters": "system.db.sql.hypotheses.max_clusters",
    "settings:system.db.sql.hypotheses.max_hypotheses": "system.db.sql.hypotheses.max_hypotheses",
}

# «Мотиваторы». Ключ называется decay, но это накопление: в _calculate_deficit
# дефицит растёт как intervals * decay_rate, поэтому в интерфейсе «Рост дефицита».
_DRIVES_ROOT = "system.db.sql.drives"
DRIVES: Dict[str, str] = {
    "settings:%s.enabled" % _DRIVES_ROOT: "%s.enabled" % _DRIVES_ROOT,
    "settings:%s.dynamic_reduction" % _DRIVES_ROOT: "%s.dynamic_reduction" % _DRIVES_ROOT,
    "settings:%s.pause_on_offline" % _DRIVES_ROOT: "%s.pause_on_offline" % _DRIVES_ROOT,
    "settings:%s.max_reflections_history" % _DRIVES_ROOT: "%s.max_reflections_history" % _DRIVES_ROOT,
    "settings:%s.max_custom_drives" % _DRIVES_ROOT: "%s.max_custom_drives" % _DRIVES_ROOT,
}
for _drive in ("curiosity", "social", "mastery"):
    for _leaf in ("enabled", "decay.rate", "decay.interval_sec"):
        _path = "%s.fundamental.%s.%s" % (_DRIVES_ROOT, _drive, _leaf)
        DRIVES["settings:" + _path] = _path

# «Рой»
SWARM: Dict[str, str] = {
    "settings:system.swarm.enabled": "system.swarm.enabled",
    "settings:system.swarm.max_concurrent_workers": "system.swarm.max_concurrent_workers",
    "settings:system.swarm.context_depth.max_steps": "system.swarm.context_depth.max_steps",
    "settings:system.swarm.context_depth.detailed_steps": "system.swarm.context_depth.detailed_steps",
}

# «Дерево мыслей»
TOT: Dict[str, str] = {
    "settings:system.tree_of_thoughts.enabled": "system.tree_of_thoughts.enabled",
    "settings:system.tree_of_thoughts.mode": "system.tree_of_thoughts.mode",
    "settings:system.tree_of_thoughts.auto_interval_steps": "system.tree_of_thoughts.auto_interval_steps",
    "settings:system.tree_of_thoughts.branches": "system.tree_of_thoughts.branches",
    "settings:system.tree_of_thoughts.simulations_per_branch": "system.tree_of_thoughts.simulations_per_branch",
    "settings:system.tree_of_thoughts.max_depth": "system.tree_of_thoughts.max_depth",
}

# «Подсознание»
SUBCONSCIOUS: Dict[str, str] = {
    "settings:system.subconscious.enabled": "system.subconscious.enabled",
    "settings:system.subconscious.patterns.consolidation.enabled": "system.subconscious.patterns.consolidation.enabled",
    "settings:system.subconscious.patterns.reflection.enabled": "system.subconscious.patterns.reflection.enabled",
    "settings:system.subconscious.patterns.forgetting.enabled": "system.subconscious.patterns.forgetting.enabled",
}

SETTINGS_FIELDS: Dict[str, str] = {
    **IDENTITY, **LLM, **MODEL_ROLES, **HEARTBEAT, **CONTEXT,
    **MEMORY, **DRIVES, **SWARM, **TOT, **SUBCONSCIOUS,
}

# .env: «Подключение к LLM» и свой провайдер для роя
ENV_FIELDS: Dict[str, str] = {
    "env:LLM_API_URL": "LLM_API_URL",
    "env:PROXY_URL": "PROXY_URL",
    "env:SUB_LLM_API_URL": "SUB_LLM_API_URL",
    # main.py собирает ключи субагентов перебором по префиксу; отдельного
    # редактора списка здесь пока нет, поэтому привязан только первый
    "env:SUB_LLM_API_KEY_1": "SUB_LLM_API_KEY_1",

    # секреты интерфейсов
    "env:AIOGRAM_BOT_TOKEN": "AIOGRAM_BOT_TOKEN",
    "env:TELETHON_API_ID": "TELETHON_API_ID",
    "env:TELETHON_API_HASH": "TELETHON_API_HASH",
    "env:GITHUB_TOKEN": "GITHUB_TOKEN",
    "env:EMAIL_ACCOUNT": "EMAIL_ACCOUNT",
    "env:EMAIL_PASSWORD": "EMAIL_PASSWORD",
    "env:TAVILY_API_KEY": "TAVILY_API_KEY",
    "env:WEBHOOK_SECRET": "WEBHOOK_SECRET",
    "env:ELEVENLABS_API_KEY": "ELEVENLABS_API_KEY",
    "env:CLOUD_WHISPER_API_KEY": "CLOUD_WHISPER_API_KEY",
    # закомментированы в .env.example: пусто = официальный API
    "env:ELEVENLABS_API_URL": "ELEVENLABS_API_URL",
    "env:CLOUD_WHISPER_API_URL": "CLOUD_WHISPER_API_URL",
}


# ---------------------------------------------------------------- интерфейсы

# Сгенерировано из config/interfaces.yaml: все 82 листовых параметра.
# Порядок соответствует файлу, чтобы сверять было проще.
INTERFACES_FIELDS: Dict[str, str] = {
    "interfaces:host.os.enabled": "host.os.enabled",
    "interfaces:host.os.desktop_interactions": "host.os.desktop_interactions",
    "interfaces:host.os.access_level": "host.os.access_level",
    "interfaces:host.os.env_access": "host.os.env_access",
    "interfaces:host.os.require_deploy_sessions": "host.os.require_deploy_sessions",
    "interfaces:host.os.deploy_max_retries": "host.os.deploy_max_retries",
    "interfaces:host.os.framework_tree_depth": "host.os.framework_tree_depth",
    "interfaces:host.os.monitoring_interval_sec": "host.os.monitoring_interval_sec",
    "interfaces:host.os.execution_timeout_sec": "host.os.execution_timeout_sec",
    "interfaces:host.os.file_read_max_chars": "host.os.file_read_max_chars",
    "interfaces:host.os.file_list_limit": "host.os.file_list_limit",
    "interfaces:host.os.top_processes_limit": "host.os.top_processes_limit",
    "interfaces:host.os.file_diff_max_chars": "host.os.file_diff_max_chars",
    "interfaces:host.os.workspace_max_opened_files": "host.os.workspace_max_opened_files",
    "interfaces:host.os.recent_file_changes_limit": "host.os.recent_file_changes_limit",
    "interfaces:host.os.workspace_max_file_chars": "host.os.workspace_max_file_chars",
    "interfaces:host.terminal.enabled": "host.terminal.enabled",
    "interfaces:host.terminal.history_limit": "host.terminal.history_limit",
    "interfaces:host.terminal.context_limit": "host.terminal.context_limit",
    "interfaces:code_graph.enabled": "code_graph.enabled",
    "interfaces:code_graph.max_search_results": "code_graph.max_search_results",
    "interfaces:code_graph.max_structure_items": "code_graph.max_structure_items",
    "interfaces:telegram.telethon.enabled": "telegram.telethon.enabled",
    "interfaces:telegram.telethon.session_name": "telegram.telethon.session_name",
    "interfaces:telegram.telethon.recent_chats_limit": "telegram.telethon.recent_chats_limit",
    "interfaces:telegram.telethon.private_chat_history_limit": "telegram.telethon.private_chat_history_limit",
    "interfaces:telegram.telethon.incoming_history_limit": "telegram.telethon.incoming_history_limit",
    "interfaces:telegram.aiogram.enabled": "telegram.aiogram.enabled",
    "interfaces:telegram.aiogram.recent_chats_limit": "telegram.aiogram.recent_chats_limit",
    "interfaces:github.enabled": "github.enabled",
    "interfaces:github.agent_account": "github.agent_account",
    "interfaces:github.request_timeout_sec": "github.request_timeout_sec",
    "interfaces:github.history_limit": "github.history_limit",
    "interfaces:github.polling_interval_sec": "github.polling_interval_sec",
    "interfaces:email.enabled": "email.enabled",
    "interfaces:email.polling_interval_sec": "email.polling_interval_sec",
    "interfaces:email.recent_limit": "email.recent_limit",
    "interfaces:web.http.enabled": "web.http.enabled",
    "interfaces:web.http.request_timeout_sec": "web.http.request_timeout_sec",
    "interfaces:web.http.max_response_chars": "web.http.max_response_chars",
    "interfaces:web.search.enabled": "web.search.enabled",
    "interfaces:web.search.search_engine": "web.search.search_engine",
    "interfaces:web.search.reader_engine": "web.search.reader_engine",
    "interfaces:web.search.request_timeout_sec": "web.search.request_timeout_sec",
    "interfaces:web.search.max_page_chars": "web.search.max_page_chars",
    "interfaces:web.search.deep_research.max_queries": "web.search.deep_research.max_queries",
    "interfaces:web.search.deep_research.max_results_per_query": "web.search.deep_research.max_results_per_query",
    "interfaces:web.search.deep_research.max_pages_to_read": "web.search.deep_research.max_pages_to_read",
    "interfaces:web.search.deep_research.total_max_chars": "web.search.deep_research.total_max_chars",
    "interfaces:web.browser.enabled": "web.browser.enabled",
    "interfaces:web.browser.headless": "web.browser.headless",
    "interfaces:web.browser.timeout_sec": "web.browser.timeout_sec",
    "interfaces:web.browser.idle_timeout_sec": "web.browser.idle_timeout_sec",
    "interfaces:web.hooks.enabled": "web.hooks.enabled",
    "interfaces:web.hooks.host": "web.hooks.host",
    "interfaces:web.hooks.port": "web.hooks.port",
    "interfaces:web.hooks.history_limit": "web.hooks.history_limit",
    "interfaces:web.hooks.preview_max_chars": "web.hooks.preview_max_chars",
    "interfaces:web.rss.enabled": "web.rss.enabled",
    "interfaces:web.rss.polling_interval_sec": "web.rss.polling_interval_sec",
    "interfaces:web.rss.recent_limit": "web.rss.recent_limit",
    "interfaces:meta.enabled": "meta.enabled",
    "interfaces:meta.access_level": "meta.access_level",
    "interfaces:meta.custom_skills_enabled": "meta.custom_skills_enabled",
    "interfaces:multimodality.enabled": "multimodality.enabled",
    "interfaces:calendar.enabled": "calendar.enabled",
    "interfaces:calendar.polling_interval_sec": "calendar.polling_interval_sec",
    "interfaces:calendar.upcoming_events_limit": "calendar.upcoming_events_limit",
    "interfaces:voice.stt.cloud.whisper.enabled": "voice.stt.cloud.whisper.enabled",
    "interfaces:voice.stt.cloud.whisper.model": "voice.stt.cloud.whisper.model",
    "interfaces:voice.stt.cloud.whisper.temperature": "voice.stt.cloud.whisper.temperature",
    "interfaces:voice.stt.cloud.whisper.timeout_sec": "voice.stt.cloud.whisper.timeout_sec",
    "interfaces:voice.tts.cloud.elevenlabs.enabled": "voice.tts.cloud.elevenlabs.enabled",
    "interfaces:voice.tts.cloud.elevenlabs.tts_model": "voice.tts.cloud.elevenlabs.tts_model",
    "interfaces:voice.tts.cloud.elevenlabs.main_voice": "voice.tts.cloud.elevenlabs.main_voice",
    "interfaces:voice.tts.cloud.elevenlabs.stability": "voice.tts.cloud.elevenlabs.stability",
    "interfaces:voice.tts.cloud.elevenlabs.similarity_boost": "voice.tts.cloud.elevenlabs.similarity_boost",
    "interfaces:voice.tts.cloud.edge.enabled": "voice.tts.cloud.edge.enabled",
    "interfaces:voice.tts.cloud.edge.main_voice": "voice.tts.cloud.edge.main_voice",
    "interfaces:voice.tts.cloud.edge.rate": "voice.tts.cloud.edge.rate",
    "interfaces:voice.tts.cloud.edge.volume": "voice.tts.cloud.edge.volume",
    "interfaces:voice.tts.cloud.edge.pitch": "voice.tts.cloud.edge.pitch",
}

# id контейнера в разметке -> путь в interfaces.yaml
INTERFACES_LISTS: Dict[str, str] = {
    "lstExcludeDirs":    "code_graph.exclude_dirs",
    "lstElevenVoices":   "voice.tts.cloud.elevenlabs.available_voices",
    "lstEdgeVoices":     "voice.tts.cloud.edge.available_voices",
}

# списки словарей: {id: (путь, порядок ключей)}
INTERFACES_OBJECT_LISTS: Dict[str, tuple] = {
    "lstFeeds": ("web.rss.feeds", ["name", "url"]),
}

# ---------------------------------------------------------------- списки

# id контейнера в разметке -> путь в settings.yaml
SETTINGS_LISTS: Dict[str, str] = {
    "modelList": "llm.available_models",
}

# id контейнера в разметке -> префикс переменных .env
ENV_LISTS: Dict[str, str] = {
    "keyList": "LLM_API_KEY_",
}


def all_settings_paths() -> List[str]:
    return list(SETTINGS_FIELDS.values())

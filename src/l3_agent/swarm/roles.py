"""
Реестр ролей субагентов (RBAC).

Хранит статические описания всех доступных в системе профессий субагентов.
Определяет их идентификаторы, названия и файлы системных промптов.
"""

from typing import List, Optional
from pydantic import BaseModel


class SubagentRole(BaseModel):
    """Модель описания роли субагента."""

    id: str  # Уникальный ID для вызова LLM
    name: str  # Человекочитаемое имя
    description: str  # Инструкция для главного агента (зачем вызывать эту роль)
    prompt_file: str  # Имя файла с промптом в папке roles/


class Subagents:
    """
    Реестр всех доступных ролей субагентов в системе.
    Определяет специализацию и доступы каждого типа работника.
    """

    CODER = SubagentRole(
        id="coder",
        name="Software Engineer",
        description="Вызывать для делегирования задач по написанию скриптов, рефакторингу, дебагу и работе с файловой системой или локальными Git-репозиториями.",
        prompt_file="CODER.md",
    )

    WEB_RESEARCHER = SubagentRole(
        id="web_researcher",
        name="OSINT Analyst",
        description="Вызывать для параллельного глубокого поиска информации в интернете, чтения статей, парсинга данных и фактчекинга.",
        prompt_file="WEB_SEARCHER.md",
    )

    ARCHIVIST = SubagentRole(
        id="archivist",
        name="Database Archivist",
        description="Вызывать для ревизии и очистки твоей памяти. Умеет читать Vector DB, удалять старый мусор и консолидировать факты.",
        prompt_file="ARCHIVIST.md",
    )

    QA_ENGINEER = SubagentRole(
        id="qa_engineer",
        name="QA Engineer",
        description="Вызывать для написания unit-тестов и проверки твоего кода на прочность. Он найдет краевые случаи и вернет список багов.",
        prompt_file="QA_ENGINEER.md",
    )

    SYSADMIN = SubagentRole(
        id="sysadmin",
        name="System Administrator",
        description="Вызывать для установки зависимостей (pip/npm), выполнения сырых shell-команд, мониторинга ОС (RAM/CPU), управления процессами и работы с сетью.",
        prompt_file="SYSADMIN.md",
    )

    @classmethod
    def all(cls) -> List[SubagentRole]:
        """Возвращает список всех зарегистрированных ролей."""
        return [v for k, v in vars(cls).items() if isinstance(v, SubagentRole)]

    @classmethod
    def get_by_id(cls, role_id: str) -> Optional[SubagentRole]:
        """Поиск роли по строковому ID (который передает LLM)."""
        for role in cls.all():
            if role.id == role_id:
                return role
        return None

from pydantic import BaseModel


class SubagentRole(BaseModel):
    id: str  # Уникальный ID для вызова LLM
    name: str  # Человекочитаемое имя
    description: str  # Инструкция для главного агента (зачем его вызывать)
    prompt_file: str  # Имя файла с промптом в папке roles/


class Subagents:
    """Реестр всех доступных ролей субагентов в системе."""

    CODER = SubagentRole(
        id="coder",
        name="Software Engineer",
        description="Субагент, которому можно делегировать задачи по написанию скриптов, рефакторингу, дебагу и работе с файловой системой или локальными Git-репозиториями.",
        prompt_file="CODER.md",
    )

    WEB_RESEARCHER = SubagentRole(
        id="web_researcher",
        name="OSINT Analyst",
        description="Вызывай его для параллельного глубокого поиска информации в интернете, чтения статей, парсинга данных и фактчекинга.",
        prompt_file="WEB_SEARCHER.md",
    )

    @classmethod
    def all(cls) -> list[SubagentRole]:
        """Возвращает список всех зарегистрированных ролей."""
        return [
            v for k, v in vars(cls).items() if isinstance(v, SubagentRole)
        ]  # Ну и заклинание...

    @classmethod
    def get_by_id(cls, role_id: str) -> SubagentRole | None:
        """Поиск роли по строковому ID (который передает LLM)."""
        for role in cls.all():
            if role.id == role_id:
                return role
        return None

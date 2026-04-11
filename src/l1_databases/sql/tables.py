from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""

    pass


class TaskTable(Base):
    """Таблица долгосрочных задач."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(primary_key=True)
    description: Mapped[str]  # Описание задачи
    term: Mapped[Optional[str]]  # Длительность
    context: Mapped[Optional[str]]  # Рабочие заметки агента


class TickTable(Base):
    """
    Таблица тиков (логов) агента.
    1 тик = мысль + массив действий + результат выполнения действий.
    """

    __tablename__ = "ticks"

    id: Mapped[str] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    thoughts: Mapped[str]

    # Хранит список словарей: [{"tool_name": "func_1", "parameters": {...}}, ...]
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    # Хранит результаты вызовов: {"func_1": "success", "func_2": "error details"}
    results: Mapped[dict[str, Any]] = mapped_column(JSON)


class PersonalityTraitTable(Base):
    """Таблица приобретенных черт личности агента."""

    __tablename__ = "personality_traits"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]  # Название черты
    description: Mapped[str]  # Описание черты
    reason: Mapped[Optional[str]]  # Причина добавления
    context: Mapped[Optional[str]]  # Контекст (в каких ситуациях применять)

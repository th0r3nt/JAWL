from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""

    pass


class TaskTable(Base):
    """Таблица долгосрочных задач (Tasks v2)."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]  # Короткое название
    description: Mapped[str]  # Полное описание задачи
    status: Mapped[str] = mapped_column(
        default="todo"
    )  # todo, in_progress, blocked, done, cancelled
    progress: Mapped[int] = mapped_column(default=0)  # 0-100%

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # Массив ID других задач
    subtasks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )  # [{"title": "...", "is_done": false}]

    due_date: Mapped[Optional[float]] = mapped_column(default=None)  # UNIX timestamp
    context: Mapped[Optional[str]] = mapped_column(default=None)  # Рабочие заметки агента


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


class MentalStateTable(Base):
    """Таблица для отслеживания состояний важных сущностей (Mental State)."""

    __tablename__ = "mental_states"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    tier: Mapped[str]  # high, medium, low, background
    category: Mapped[str]  # subject, object

    # Автоматическое обновление времени при любых изменениях
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    description: Mapped[str]
    status: Mapped[str]
    context: Mapped[Optional[str]]
    related_information: Mapped[Optional[str]]


class DriveTable(Base):
    """Таблица внутренних мотиваторов агента (Drives)."""

    __tablename__ = "drives"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]  # "fundamental" (постоянные) или "custom" (созданные самим агентом)
    description: Mapped[str]
    decay_rate: Mapped[float]  # Скорость роста дефицита (% в час)

    # Время последнего удовлетворения мотивации (UTC)
    last_satisfied_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # Хранит список строк (последние рефлексии агента)
    recent_reflections: Mapped[list[str]] = mapped_column(JSON, default=list)

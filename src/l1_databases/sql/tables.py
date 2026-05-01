"""
Декларативное описание схем реляционных таблиц (SQLAlchemy ORM).

Определяет структуру всех сущностей долговременной структурированной
памяти агента (Задачи, Логи, Черты личности, Состояния и Мотиваторы).
"""

from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""

    pass


class TaskTable(Base):
    """
    Таблица долгосрочных задач (Tasks).
    Используется для декомпозиции глобальных целей агента.
    """

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
    )  # Массив ID других задач, блокирующих эту
    subtasks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )  # [{"title": "...", "is_done": false}]

    due_date: Mapped[Optional[float]] = mapped_column(default=None)  # UNIX timestamp
    context: Mapped[Optional[str]] = mapped_column(default=None)  # Рабочие заметки агента


class TickTable(Base):
    """
    Таблица тиков (логов) агента.
    1 тик = Итерация цикла (Мысли + Массив действий + Результат выполнения).
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
    """
    Таблица приобретенных черт личности агента.
    Позволяет агенту динамически адаптироваться под пользователя.
    """

    __tablename__ = "personality_traits"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]  # Название черты
    description: Mapped[str]  # Описание черты
    reason: Mapped[Optional[str]]  # Причина добавления (контекст формирования)
    context: Mapped[Optional[str]]  # В каких ситуациях применять


class MentalStateTable(Base):
    """
    Таблица для отслеживания состояний важных сущностей (Mental State).
    Аналог CRM-системы агента для отслеживания статусов серверов, людей или процессов.
    """

    __tablename__ = "mental_states"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    tier: Mapped[str]  # high, medium, low, background
    category: Mapped[str]  # subject, object

    # Автоматическое обновление времени при любых изменениях (onupdate)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    description: Mapped[str]
    status: Mapped[str]
    context: Mapped[Optional[str]]
    related_information: Mapped[Optional[str]]


class DriveTable(Base):
    """
    Таблица внутренних мотиваторов агента (Drives).
    Обеспечивает математическую модель проактивности при отсутствии команд от пользователя.
    """

    __tablename__ = "drives"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]  # "fundamental" (системные) или "custom" (созданные самим агентом)
    description: Mapped[str]
    decay_rate: Mapped[float]  # Скорость роста дефицита (% в интервал)

    # Время последнего удовлетворения мотивации (UTC)
    last_satisfied_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # Хранит список строк (последние текстовые рефлексии агента)
    recent_reflections: Mapped[list[str]] = mapped_column(JSON, default=list)

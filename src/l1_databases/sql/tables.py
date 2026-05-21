"""
Declarative schema description of relational tables (SQLAlchemy ORM).

Defines the structure of all long-term structured memory entities
of the agent (Tasks, Logs, Personality Traits, States, and Motivators).
"""

from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class TaskTable(Base):
    """
    Long-term tasks table (Tasks).
    Used for decomposing global goals of the agent.
    """

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]  # Short title
    description: Mapped[str]  # Full description of the task
    status: Mapped[str] = mapped_column(
        default="todo"
    )  # todo, in_progress, blocked, done, cancelled
    progress: Mapped[int] = mapped_column(default=0)  # 0-100%

    # Eisenhower matrix quadrant (1-4)
    quadrant: Mapped[int] = mapped_column(default=2)

    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[list[str]] = mapped_column(
        JSON, default=list
    )  # Array of other task IDs blocking this one
    subtasks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list
    )  # [{"title": "...", "is_done": false}]

    due_date: Mapped[Optional[float]] = mapped_column(default=None)  # UNIX timestamp
    context: Mapped[Optional[str]] = mapped_column(
        default=None
    )  # Operational notes of the agent


class NoteTable(Base):
    """
    Notes table (Working Memory / Scratchpad).
    Intended for storing operational information that is always
    displayed in the agent's system prompt.
    """

    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(primary_key=True)
    content: Mapped[str]

    # Automatic time update upon any changes (onupdate)
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )


class TickTable(Base):
    """
    Agent ticks (logs) table.
    1 tick = Loop iteration (Thoughts + Array of actions + Execution result).
    """

    __tablename__ = "ticks"

    id: Mapped[str] = mapped_column(primary_key=True)

    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(timezone.utc))
    thoughts: Mapped[str]

    # Stores list of dicts: [{"tool_name": "func_1", "parameters": {...}}, ...]
    actions: Mapped[list[dict[str, Any]]] = mapped_column(JSON)

    # Stores execution results: {"func_1": "success", "func_2": "error details"}
    results: Mapped[dict[str, Any]] = mapped_column(JSON)


class PersonalityTraitTable(Base):
    """
    Table of acquired personality traits of the agent.
    Allows the agent to dynamically adapt to the user.
    """

    __tablename__ = "personality_traits"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]  # Trait name
    description: Mapped[str]  # Trait description
    reason: Mapped[Optional[str]]  # Reason for adding (context of formation)
    context: Mapped[Optional[str]]  # Situations where this applies


class MentalStateTable(Base):
    """
    Table for tracking states of important entities (Mental State).
    Analogue of the agent's CRM system for tracking server, human, or process statuses.
    """

    __tablename__ = "mental_states"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    tier: Mapped[str]  # high, medium, low, background
    category: Mapped[str]  # subject, object

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    description: Mapped[str]
    status: Mapped[str]
    context: Mapped[Optional[str]]
    related_information: Mapped[Optional[str]]

    attitude: Mapped[str] = mapped_column(default="Neutral")  # Agent attitude
    directives: Mapped[str] = mapped_column(default="")  # Interaction guidelines
    epistemic_state: Mapped[str] = mapped_column(
        default=""
    )  # Theory of Mind: knowledge of what the subject knows/does not know
    relations: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict
    )  # Relations {"SUBJECT_ID": "Reason"}


class DriveTable(Base):
    """
    Table of internal motivators of the agent (Drives).
    Provides a mathematical model of proactivity in the absence of user commands.
    """

    __tablename__ = "drives"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]  # "fundamental" (system-level) or "custom" (created by the agent itself)
    description: Mapped[str]

    decay_rate: Mapped[float]  # Deficit decay rate (% per interval)
    decay_interval_sec: Mapped[int] = mapped_column(default=3600)  # Interval duration

    # Time of last drive satisfaction (UTC)
    last_satisfied_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    # Stores list of strings (latest reflections of the agent)
    recent_reflections: Mapped[list[str]] = mapped_column(JSON, default=list)


class BayesianHypothesisTable(Base):
    """
    Bayesian hypotheses table.
    Used by the agent for deductive investigation and probabilistic reasoning.
    """

    __tablename__ = "bayesian_hypotheses"

    id: Mapped[str] = mapped_column(primary_key=True)
    cluster_name: Mapped[str] = mapped_column(default="General investigation")
    title: Mapped[str]
    prior_probability: Mapped[float]
    current_probability: Mapped[float]

    # Stores list of evidence: [{"evidence": "Text", "tpr": 0.9, "fpr": 0.1, "new_prob": 0.85}]
    evidence_log: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

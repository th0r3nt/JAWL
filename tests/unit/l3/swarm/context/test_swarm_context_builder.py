"""
Unit-тесты для сборщика контекста субагентов (SwarmContextBuilder).

Проверяют корректность фильтрации навыков (RBAC) и форматирования
локальной истории с учетом лимитов сжатия (Context Truncation).
"""

import pytest
from typing import List, Dict

from src.l3_agent.swarm.roles import SubagentRole
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.utils.settings import SwarmContextDepthConfig
from src.l3_agent.skills.registry import _REGISTRY


@pytest.fixture
def dummy_role() -> SubagentRole:
    """Фикстура: базовая роль субагента для тестов."""
    return SubagentRole(
        id="tester",
        name="Test Engineer",
        description="Test role for unit tests.",
        prompt_file="DUMMY.md",
    )


@pytest.fixture
def context_config() -> SwarmContextDepthConfig:
    """Фикстура: конфигурация лимитов обрезки контекста."""
    return SwarmContextDepthConfig(
        max_steps=3,
        detailed_steps=1,
        action_max_chars=50,
        result_max_chars=50,
        thoughts_short_max_chars=20,
        action_short_max_chars=15,
        result_short_max_chars=15,
    )


@pytest.fixture(autouse=True)
def mock_registry():
    """Фикстура: мокает глобальный реестр скиллов для изоляции тестов."""
    original = _REGISTRY.copy()
    _REGISTRY.clear()

    _REGISTRY["Skill.allowed"] = {"doc_string": "`Skill.allowed()` - Разрешенный навык."}
    _REGISTRY["Skill.forbidden"] = {"doc_string": "`Skill.forbidden()` - Запрещенный навык."}
    _REGISTRY["SubagentReport.submit_final_report"] = {
        "doc_string": "`submit_final_report()` - Отчет."
    }

    yield

    _REGISTRY.clear()
    _REGISTRY.update(original)


def test_swarm_context_builder_filters_skills(
    dummy_role: SubagentRole, context_config: SwarmContextDepthConfig
) -> None:
    """
    Проверяет, что сборщик контекста включает в промпт только разрешенные
    для данной роли навыки (RBAC) и системный навык отчета.
    """
    allowed_skills = ["Skill.allowed"]
    builder = SwarmContextBuilder(
        role=dummy_role,
        allowed_skills=allowed_skills,
        config=context_config,
    )

    context = builder.build(
        subagent_id="test_id_123", task_description="Do testing", history=[]
    )

    assert "`Skill.allowed()` - Разрешенный навык." in context
    assert "`submit_final_report()` - Отчет." in context
    assert "Skill.forbidden" not in context


def test_swarm_context_builder_history_formatting(
    dummy_role: SubagentRole, context_config: SwarmContextDepthConfig
) -> None:
    """
    Проверяет, что история действий обрезается по лимитам из SwarmContextDepthConfig,
    причем старые шаги сжимаются сильнее, чем свежие (детальные).
    """
    builder = SwarmContextBuilder(
        role=dummy_role,
        allowed_skills=[],
        config=context_config,
    )

    history: List[Dict[str, str]] = [
        {
            "thoughts": "Old thought that is very very very long and should be truncated because it exceeds the limit of 20 chars.",
            "actions": "Old action",
            "results": "Old result that is too long.",
        },
        {"thoughts": "Second thought", "actions": "Second action", "results": "Second result"},
        {
            "thoughts": "Fresh detailed thought that should NOT be truncated even if it is very long because detailed_steps=1.",
            "actions": "Fresh action",
            "results": "Fresh result",
        },
    ]

    context = builder.build(subagent_id="test_id", task_description="Task", history=history)

    # Старый шаг должен быть обрезан
    assert "Old thought that is " in context
    assert "обрезаны системой" in context

    # Свежий шаг не должен резаться
    assert "Fresh detailed thought that should NOT be truncated" in context

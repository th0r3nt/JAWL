import pytest
from unittest.mock import patch
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.l3_agent.swarm.roles import SubagentRole


@pytest.fixture
def dummy_role():
    return SubagentRole(
        id="tester", name="Tester", description="Tests stuff", prompt_file="TEST.md"
    )


@patch("src.l3_agent.swarm.context.builder._REGISTRY")
def test_swarm_context_builder_filters_skills(mock_registry, dummy_role):
    mock_registry.__contains__.side_effect = lambda k: k in [
        "Allowed.skill",
        "SubagentReport.submit_final_report",
        "Forbidden.skill",
    ]
    mock_registry.__getitem__.side_effect = lambda k: {"doc_string": f"Docs for {k}"}

    builder = SwarmContextBuilder(role=dummy_role, allowed_skills=["Allowed.skill"])

    context = builder.build(subagent_id="123", task_description="Do it", history=[])

    assert "Your Subagent ID: 123" in context
    assert "Your Role: TESTER" in context
    assert "Do it" in context

    assert "Docs for Allowed.skill" in context
    assert "Docs for SubagentReport.submit_final_report" in context
    assert "Forbidden.skill" not in context


def test_swarm_context_builder_history_formatting(dummy_role):
    builder = SwarmContextBuilder(role=dummy_role, allowed_skills=[])

    history = [
        {"thoughts": "Думаю", "actions": "action()", "results": "ok"},
        {"thoughts": "Второе", "actions": "None", "results": "fail"},
    ]

    context = builder.build("123", "Task", history)

    assert "### STEP 1" in context
    assert "*Thoughts*: Думаю" in context
    assert "### STEP 2" in context
    assert "*Results*:\n```\nfail\n```" in context

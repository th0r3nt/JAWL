import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.l3_agent.swarm.loop import SubagentLoop
from src.l3_agent.swarm.roles import Subagents


@pytest.fixture
def mock_loop_deps(mock_executor):
    return {
        "subagent_id": "123",
        "role": Subagents.CODER,
        "task_description": "Task",
        "executor": mock_executor,
        "model_name": "test-model",
        "prompt_builder": MagicMock(build=MagicMock(return_value="System")),
        "context_builder": MagicMock(build=MagicMock(return_value="Context")),
        "allowed_skills": ["Allowed.tool"],
        "max_steps": 3,
    }


@pytest.mark.asyncio
async def test_subagent_graceful_exit(mock_loop_deps):
    loop = SubagentLoop(**mock_loop_deps)
    loop.report_submitted = True

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is True
    assert len(loop.history) == 0


@pytest.mark.asyncio
async def test_subagent_forces_report_submission(mock_loop_deps):
    loop = SubagentLoop(**mock_loop_deps)
    loop.max_steps = 2
    loop.report_submitted = False

    # Модель настойчиво пытается выйти (empty actions list)
    loop.executor.execute.return_value = '{"reflection": "Я хочу уйти", "actions": []}'

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is False
    assert len(loop.history) == 2
    assert "[System Error]" in loop.history[0]["results"]
    assert "This is forbidden." in loop.history[0]["results"]


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.loop.call_skill", new_callable=AsyncMock)
async def test_subagent_llm_crash_forces_report(mock_call_skill, mock_loop_deps):
    loop = SubagentLoop(**mock_loop_deps)
    # Экзекутор возвращает None (фатальный краш)
    loop.executor.execute.return_value = None

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    mock_call_skill.assert_called_once()
    assert mock_call_skill.call_args[0][0] == "SubagentReport.submit_final_report"

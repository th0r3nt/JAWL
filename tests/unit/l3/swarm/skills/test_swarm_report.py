import pytest
from unittest.mock import AsyncMock, MagicMock
from src.utils.event.registry import Events
from src.l3_agent.swarm.skills.report import SubagentReport


@pytest.mark.asyncio
async def test_subagent_report_submit(tmp_path):
    """Тест: Отчет сохраняется на диск, а главный агент получает уведомление через EventBus."""
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    sandbox_dir = tmp_path / "sandbox"

    report_skill = SubagentReport(event_bus=mock_bus, sandbox_dir=sandbox_dir)

    res = await report_skill.submit_final_report("abc12", "coder", "# My Report")

    # Проверка ответа скилла
    assert res.is_success is True
    assert "пустой массив" in res.message

    # Проверка сохранения файла
    report_file = sandbox_dir / "_system" / "subagents" / "coder_abc12.md"
    assert report_file.exists()
    assert report_file.read_text(encoding="utf-8") == "# My Report"

    # Проверка уведомления
    mock_bus.publish.assert_called_once()
    args = mock_bus.publish.call_args[1]
    assert mock_bus.publish.call_args[0][0] == Events.SUBAGENT_TASK_COMPLETED
    assert args["subagent_id"] == "abc12"
    assert args["role"] == "coder"
    assert "coder_abc12.md" in args["message"]


@pytest.mark.asyncio
async def test_subagent_report_rejects_path_traversal_role(tmp_path):
    """role не должен позволять записывать отчет вне reports_dir."""
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    sandbox_dir = tmp_path / "sandbox"
    report_skill = SubagentReport(event_bus=mock_bus, sandbox_dir=sandbox_dir)

    res = await report_skill.submit_final_report("outside", "../../../", "PWN")

    assert res.is_success is False
    assert not (tmp_path / "_outside.md").exists()
    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_subagent_report_rejects_path_traversal_id(tmp_path):
    """subagent_id не должен позволять записывать отчет вне reports_dir."""
    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    sandbox_dir = tmp_path / "sandbox"
    report_skill = SubagentReport(event_bus=mock_bus, sandbox_dir=sandbox_dir)

    res = await report_skill.submit_final_report("../../../outside", "coder", "PWN")

    assert res.is_success is False
    assert not (tmp_path / "outside.md").exists()
    mock_bus.publish.assert_not_called()

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.l0_state.agent.state import AgentStatus
from src.l3_agent.react.loop import ReactLoop


def test_react_dump_context_to_file(mock_dependencies):
    loop = ReactLoop(**mock_dependencies)
    messages = [
        {"role": "system", "content": "You are AI"},
        {"role": "user", "content": "Hello"},
    ]
    with patch("builtins.open") as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file
        loop._dump_context_to_file(messages)
        args, kwargs = mock_open.call_args
        assert str(args[0]).replace("\\", "/") == "logs/prompts/main_prompt.md"


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_empty_actions_exit(mock_execute_skill, mock_dependencies):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Мокаем экзекутор, чтобы он вернул пустой список действий
    deps["executor"].execute.return_value = (
        '{"reflection": "Мне нечего делать.", "actions": []}'
    )

    await loop.run("HEARTBEAT", {}, missed_events=[])

    assert deps["agent_state"].state == AgentStatus.IDLE
    mock_execute_skill.assert_not_called()
    deps["sql_ticks"].save_tick.assert_awaited_once()
    assert deps["agent_state"].current_step == 1


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_max_steps_limit(mock_execute_skill, mock_dependencies):
    deps = mock_dependencies
    deps["agent_state"].max_react_steps = 2
    loop = ReactLoop(**deps)

    deps["executor"].execute.return_value = (
        '{"reflection": "Делаю шаг", "actions": [{"tool_name": "test", "parameters": {}}]}'
    )
    mock_execute_skill.return_value = "Result"

    await loop.run("TEST", {}, missed_events=[])

    assert deps["executor"].execute.call_count == 2
    assert deps["agent_state"].current_step == 3


@pytest.mark.asyncio
async def test_react_inject_images_success(mock_dependencies, tmp_path):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"hello")

    loop.agent_state.last_actions_result = (
        f"Result:[SYSTEM_MARKER_IMAGE_ATTACHED: {fake_img.resolve()}]"
    )

    messages = [
        {"role": "system", "content": "Система"},
        {"role": "user", "content": "Анализируй"},
    ]

    result = await loop._inject_images_to_payload(messages.copy())
    last_msg_content = result[-1]["content"]

    assert isinstance(last_msg_content, list)
    assert last_msg_content[0]["type"] == "text"
    assert last_msg_content[1]["type"] == "image_url"

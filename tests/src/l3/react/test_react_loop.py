import pytest
import openai
from unittest.mock import AsyncMock, MagicMock, patch

from src.l0_state.agent.state import AgentStatus
from src.l3_agent.react.loop import ReactLoop


def test_react_dump_context_to_file(mock_dependencies):
    """Тест: Запись системного промпта в файл логов (last_prompt.md) работает безопасно."""
    loop = ReactLoop(**mock_dependencies)

    messages = [
        {"role": "system", "content": "You are AI"},
        {"role": "user", "content": "Hello"},
    ]

    # Мокаем встроенную функцию open
    with patch("builtins.open") as mock_open:
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        loop._dump_context_to_file(messages)

        mock_open.assert_called_once_with("logs/last_prompt.md", "w", encoding="utf-8")

        # Проверяем, что все сообщения были записаны
        written_content = "".join([call[0][0] for call in mock_file.write.call_args_list])
        assert "### Role: system" in written_content
        assert "You are AI" in written_content
        assert "### Role: user" in written_content
        assert "Hello" in written_content


def test_react_dump_context_exception_safety(mock_dependencies):
    """Тест: Если файл недоступен, дамп падает тихо и не ломает цикл агента."""
    loop = ReactLoop(**mock_dependencies)

    with patch("builtins.open", side_effect=PermissionError("Access Denied")):
        # Не должно выкинуть Exception наверх
        loop._dump_context_to_file([{"role": "system", "content": "1"}])


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_empty_actions_exit(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
        '{"thoughts": "Мне нечего делать.", "actions": []}'
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("HEARTBEAT", {}, missed_events=[])

    assert deps["agent_state"].state == AgentStatus.IDLE
    mock_execute_skill.assert_not_called()
    deps["sql_ticks"].save_tick.assert_awaited_once()
    assert deps["agent_state"].current_step == 1


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_invalid_json_retry(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    loop = ReactLoop(**deps)
    mock_session = AsyncMock()

    mock_session.chat.completions.create.side_effect = [
        mock_openai_response("{broken json}"),
        mock_openai_response('{"thoughts": "Починил.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    assert mock_session.chat.completions.create.call_count == 2
    assert deps["agent_state"].current_step == 2

    # Проверяем, что ошибка JSON была записана в базу тиков
    call_args = deps["sql_ticks"].save_tick.call_args_list[0]
    assert "Format Error" in call_args[1]["results"]["execution_report"]


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_max_steps_limit(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    deps["agent_state"].max_react_steps = 2
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
        '{"thoughts": "Делаю шаг", "actions": [{"tool_name": "test", "parameters": {}}]}'
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)
    mock_execute_skill.return_value = "Result"

    await loop.run("TEST", {}, missed_events=[])

    assert mock_session.chat.completions.create.call_count == 2
    # Цикл оборвался, потому что 3 > 2 (лимит достигнут)
    assert deps["agent_state"].current_step == 3


@pytest.mark.asyncio
async def test_react_rate_limit(mock_dependencies, mock_openai_response):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session1 = AsyncMock()
    mock_session1.api_key = "key_1"
    rate_limit_err = openai.RateLimitError("429", response=MagicMock(), body={})
    mock_session1.chat.completions.create.side_effect = rate_limit_err

    mock_session2 = AsyncMock()
    mock_session2.api_key = "key_2"
    mock_session2.chat.completions.create.return_value = mock_openai_response(
        '{"thoughts": "ok", "actions": []}'
    )

    deps["llm_client"].get_session = MagicMock(side_effect=[mock_session1, mock_session2])

    await loop.run("TEST", {}, missed_events=[])

    deps["llm_client"].rotator.cooldown_key.assert_called_once_with("key_1", 60)
    assert deps["agent_state"].state == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_react_auth_error_ban_key(mock_dependencies, mock_openai_response):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.api_key = "dead_key"
    auth_err = openai.AuthenticationError("401", response=MagicMock(), body={})

    mock_session.chat.completions.create.side_effect = [
        auth_err,
        mock_openai_response('{"thoughts": "ok", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])
    deps["llm_client"].rotator.ban_key.assert_called_once_with("dead_key")


@pytest.mark.asyncio
async def test_react_no_tool_calls(mock_dependencies, mock_openai_response):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
        "Я просто хочу поболтать.", finish_reason="stop"
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])
    assert deps["agent_state"].state == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_react_inject_images_no_markers(mock_dependencies):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Стейт пустой - инжекта не будет
    loop.agent_state.last_actions_result = "Обычный ответ тулзы"

    messages = [
        {"role": "system", "content": "Система"},
        {"role": "user", "content": "Контекст агента"},
    ]

    result = await loop._inject_images_to_payload(messages.copy())

    assert result == messages
    assert isinstance(result[-1]["content"], str)


@pytest.mark.asyncio
async def test_react_inject_images_success(mock_dependencies, tmp_path):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"hello")

    # Маркер теперь лежит в результатах последнего действия стейта
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
    assert last_msg_content[0]["text"] == "Анализируй"
    assert last_msg_content[1]["type"] == "image_url"
    assert "aGVsbG8=" in last_msg_content[1]["image_url"]["url"]


@pytest.mark.asyncio
async def test_react_timeout_retry(mock_dependencies, mock_openai_response):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.api_key = "key_1"

    timeout_err = openai.APITimeoutError(request=MagicMock())
    mock_session.chat.completions.create.side_effect = [
        timeout_err,
        mock_openai_response('{"thoughts": "ok", "actions": []}'),
    ]

    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    assert mock_session.chat.completions.create.call_count == 2
    assert deps["agent_state"].current_step == 1
    assert deps["agent_state"].state == AgentStatus.IDLE

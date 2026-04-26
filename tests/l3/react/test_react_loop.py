import pytest
import openai
from unittest.mock import AsyncMock, MagicMock, patch

from src.l0_state.agent.state import AgentStatus
from src.l3_agent.react.loop import ReactLoop


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
        mock_openai_response("{broken json"),
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
async def test_react_parses_xmlish_actions_parameter(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    loop = ReactLoop(**deps)
    mock_session = AsyncMock()
    mock_execute_skill.return_value = "ok"

    mock_session.chat.completions.create.side_effect = [
        mock_openai_response(
            """
Поставлю безопасную реакцию.</thoughts>
<parameter name="actions">[
  {
    "tool_name": "KurigramReactions.set_reaction",
    "parameters": {"chat_id": 1234567890, "message_id": 609, "reaction": "🗿"}
  }
]
""".strip()
        ),
        mock_openai_response('{"thoughts": "Готово.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    mock_execute_skill.assert_awaited_once()
    actions = mock_execute_skill.await_args.kwargs["actions"]
    assert actions[0].tool_name == "KurigramReactions.set_reaction"
    assert actions[0].parameters["reaction"] == "🗿"
    assert deps["agent_state"].current_step == 2


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_empty_actions_reads_unread_telegram_dashboard(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    deps["context_builder"].build.return_value = """
### TELEGRAM USER API [ON]
Account info: Профиль: 1 1
---
[User] UnreadUser (ID: 1234567890) [UNREAD: 2]
[User] Operator (ID: 987654321)


### AIOGRAM [OFF]
Интерфейс отключен.
""".strip()
    loop = ReactLoop(**deps)
    mock_session = AsyncMock()
    mock_execute_skill.return_value = "chat read"

    mock_session.chat.completions.create.side_effect = [
        mock_openai_response('{"thoughts": "Пустой хартбит.", "actions": []}'),
        mock_openai_response('{"thoughts": "Теперь всё.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("HEARTBEAT", {}, missed_events=[])

    mock_execute_skill.assert_awaited_once()
    actions = mock_execute_skill.await_args.kwargs["actions"]
    assert actions[0].tool_name == "KurigramChats.read_chat"
    assert actions[0].parameters == {"chat_id": 1234567890, "limit": 10}
    assert deps["agent_state"].current_step == 2


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_empty_actions_reads_unread_telegram_list_format(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    deps = mock_dependencies
    deps["context_builder"].build.return_value = """
### TELEGRAM USER API [ON]
Непрочитанные чаты:
- User | ID: `1234567890` | UnreadUser | UNREAD: 2


### AIOGRAM [OFF]
Интерфейс отключен.
""".strip()
    loop = ReactLoop(**deps)
    mock_session = AsyncMock()
    mock_execute_skill.return_value = "chat read"

    mock_session.chat.completions.create.side_effect = [
        mock_openai_response('{"thoughts": "Пусто.", "actions": []}'),
        mock_openai_response('{"thoughts": "Готово.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("HEARTBEAT", {}, missed_events=[])

    mock_execute_skill.assert_awaited_once()
    actions = mock_execute_skill.await_args.kwargs["actions"]
    assert actions[0].tool_name == "KurigramChats.read_chat"
    assert actions[0].parameters == {"chat_id": 1234567890, "limit": 10}


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


def test_react_inject_images_no_markers(mock_dependencies):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Стейт пустой - инжекта не будет
    loop.agent_state.last_actions_result = "Обычный ответ тулзы"

    messages = [
        {"role": "system", "content": "Система"},
        {"role": "user", "content": "Контекст агента"},
    ]

    result = loop._inject_images_to_payload(messages.copy())

    assert result == messages
    assert isinstance(result[-1]["content"], str)


def test_react_inject_images_success(mock_dependencies, tmp_path):
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"hello")

    # Маркер теперь лежит в результатах последнего действия стейта
    loop.agent_state.last_actions_result = (
        f"Result: [SYSTEM_MARKER_IMAGE_ATTACHED: {fake_img.resolve()}]"
    )

    messages = [
        {"role": "system", "content": "Система"},
        {"role": "user", "content": "Анализируй"},
    ]

    result = loop._inject_images_to_payload(messages.copy())
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

import pytest
import openai
from unittest.mock import AsyncMock, MagicMock, patch

from src.l0_state.agent.state import AgentState, AgentStatus
from src.l3_agent.react.loop import ReactLoop


# ===================================================================
# ФИКСТУРЫ И ХЕЛПЕРЫ
# ===================================================================


@pytest.fixture
def mock_dependencies():
    """Создает безопасные заглушки для всех зависимостей ReactLoop."""
    llm_client = MagicMock()
    llm_client.rotator = MagicMock()

    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "System Prompt"

    context_builder = AsyncMock()
    context_builder.build.return_value = "User Context"

    agent_state = AgentState(max_react_steps=3)

    sql_ticks = AsyncMock()
    token_tracker = MagicMock()

    # Фейковая схема
    tools = [{"type": "function", "function": {"name": "execute_skill"}}]

    cooldown_sec = 2

    return {
        "llm_client": llm_client,
        "prompt_builder": prompt_builder,
        "context_builder": context_builder,
        "agent_state": agent_state,
        "sql_ticks": sql_ticks,
        "token_tracker": token_tracker,
        "tools": tools,
        "cooldown_sec": cooldown_sec,
    }


def create_mock_openai_response(arguments_json: str, finish_reason: str = "tool_calls"):
    """Создает фейковый ответ от OpenAI API."""
    response = MagicMock()
    message = MagicMock()

    if finish_reason == "tool_calls":
        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "execute_skill"
        tool_call.function.arguments = arguments_json
        message.tool_calls = [tool_call]
    else:
        message.tool_calls = None
        message.content = arguments_json

    response.choices = [MagicMock(message=message)]
    return response


# ===================================================================
# ТЕСТЫ
# ===================================================================


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_empty_actions_exit(mock_execute_skill, mock_dependencies):
    """
    Тест: Если LLM возвращает пустой массив 'actions',
    цикл должен завершиться и сохранить тик.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Мокаем сессию и ответ LLM
    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = create_mock_openai_response(
        '{"thoughts": "Мне нечего делать.", "actions": []}'
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("HEARTBEAT", {}, missed_events=[])

    # Проверки
    assert deps["agent_state"].state == AgentStatus.IDLE
    mock_execute_skill.assert_not_called()  # Ничего не исполняли
    deps["sql_ticks"].save_tick.assert_awaited_once()  # Мысль сохранена в БД

    # Шаг должен остаться = 1, так как цикл сразу завершился
    assert deps["agent_state"].current_step == 1


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_invalid_json_retry(mock_execute_skill, mock_dependencies):
    """
    Тест: Если LLM отдает битый JSON, агент ловит JSONDecodeError,
    добавляет сообщение об ошибке в контекст и пробует снова (сжигая шаг).
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()

    # Первый вызов - кривой JSON. Второй вызов - правильный с пустыми actions (выход).
    mock_session.chat.completions.create.side_effect = [
        create_mock_openai_response("{broken json"),
        create_mock_openai_response('{"thoughts": "Починил.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # LLM была вызвана 2 раза
    assert mock_session.chat.completions.create.call_count == 2
    # Шаг должен увеличиться, так как ошибка JSON "сжигает" попытку, защищая от бесконечного цикла
    assert deps["agent_state"].current_step == 2


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_max_steps_limit(mock_execute_skill, mock_dependencies):
    """
    Тест: Защита от зацикливания. Если LLM вызывает инструменты max_steps раз подряд,
    цикл должен принудительно завершиться.
    """
    deps = mock_dependencies
    deps["agent_state"].max_react_steps = 2  # Лимит 2 шага
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = create_mock_openai_response(
        '{"thoughts": "Делаю шаг", "actions": [{"tool_name": "test", "parameters": {}}]}'
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)
    mock_execute_skill.return_value = "Result"

    await loop.run("TEST", {}, missed_events=[])

    # LLM должна быть вызвана ровно max_react_steps раз (2 раза)
    assert mock_session.chat.completions.create.call_count == 2
    # current_step обновляется в начале итерации, поэтому после выхода он остается равным 2
    assert deps["agent_state"].current_step == 2


@pytest.mark.asyncio
async def test_react_rate_limit(mock_dependencies):
    """
    Тест: Ошибка 429 (Rate Limit). Ключ должен отправиться в кулдаун,
    а цикл должен попытаться запросить другую сессию.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session1 = AsyncMock()
    mock_session1.api_key = "key_1"
    # Создаем фейковую ошибку RateLimit (в OpenAI v1 она требует request/response объекты, мокаем)
    rate_limit_err = openai.RateLimitError("429", response=MagicMock(), body={})
    mock_session1.chat.completions.create.side_effect = rate_limit_err

    mock_session2 = AsyncMock()
    mock_session2.api_key = "key_2"
    mock_session2.chat.completions.create.return_value = create_mock_openai_response(
        '{"thoughts": "ok", "actions": []}'
    )

    # Ротатор выдает сначала session1, затем session2
    deps["llm_client"].get_session = MagicMock(side_effect=[mock_session1, mock_session2])

    await loop.run("TEST", {}, missed_events=[])

    # Проверяем, что первый ключ ушел в кулдаун
    deps["llm_client"].rotator.cooldown_key.assert_called_once_with("key_1", 60)
    # Проверяем, что цикл успешно прошел дальше со вторым ключом
    assert deps["agent_state"].state == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_react_auth_error_ban_key(mock_dependencies):
    """
    Тест: Ошибка 401 (Auth Error). Мертвый ключ должен быть удален навсегда.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.api_key = "dead_key"
    auth_err = openai.AuthenticationError("401", response=MagicMock(), body={})

    mock_session.chat.completions.create.side_effect = [
        auth_err,
        create_mock_openai_response('{"thoughts": "ok", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # Проверяем, что ключ был забанен
    deps["llm_client"].rotator.ban_key.assert_called_once_with("dead_key")


@pytest.mark.asyncio
async def test_react_no_tool_calls(mock_dependencies):
    """
    Тест: Если LLM затупила и ответила просто текстом (без вызова функций),
    цикл должен прерваться, чтобы не застрять.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    # Возвращаем ответ без tool_calls
    mock_session.chat.completions.create.return_value = create_mock_openai_response(
        "Я просто хочу поболтать.", finish_reason="stop"
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # Стейт должен вернуться в IDLE без ошибок и без вызова функций
    assert deps["agent_state"].state == AgentStatus.IDLE
    deps["sql_ticks"].save_tick.assert_not_called()

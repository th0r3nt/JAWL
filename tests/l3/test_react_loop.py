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
    """
    Тест: Если LLM возвращает пустой массив 'actions',
    цикл должен завершиться и сохранить тик.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Мокаем сессию и ответ LLM
    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
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
async def test_react_invalid_json_retry(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    """
    Тест: Если LLM отдает битый JSON, агент ловит JSONDecodeError,
    добавляет сообщение об ошибке в контекст и пробует снова (сжигая шаг).
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()

    # Первый вызов - кривой JSON. Второй вызов - правильный с пустыми actions (выход).
    mock_session.chat.completions.create.side_effect = [
        mock_openai_response("{broken json"),
        mock_openai_response('{"thoughts": "Починил.", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # LLM была вызвана 2 раза
    assert mock_session.chat.completions.create.call_count == 2
    # Шаг должен увеличиться, так как ошибка JSON "сжигает" попытку, защищая от бесконечного цикла
    assert deps["agent_state"].current_step == 2


@pytest.mark.asyncio
@patch("src.l3_agent.react.loop.execute_skill", new_callable=AsyncMock)
async def test_react_max_steps_limit(
    mock_execute_skill, mock_dependencies, mock_openai_response
):
    """
    Тест: Защита от зацикливания. Если LLM вызывает инструменты max_steps раз подряд,
    цикл должен принудительно завершиться.
    """
    deps = mock_dependencies
    deps["agent_state"].max_react_steps = 2  # Лимит 2 шага
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
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
async def test_react_rate_limit(mock_dependencies, mock_openai_response):
    """
    Тест: Ошибка 429 (Rate Limit). Ключ должен отправиться в кулдаун,
    а цикл должен попытаться запросить другую сессию.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session1 = AsyncMock()
    mock_session1.api_key = "key_1"
    # Создаем фейковую ошибку RateLimit
    rate_limit_err = openai.RateLimitError("429", response=MagicMock(), body={})
    mock_session1.chat.completions.create.side_effect = rate_limit_err

    mock_session2 = AsyncMock()
    mock_session2.api_key = "key_2"
    mock_session2.chat.completions.create.return_value = mock_openai_response(
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
async def test_react_auth_error_ban_key(mock_dependencies, mock_openai_response):
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
        mock_openai_response('{"thoughts": "ok", "actions": []}'),
    ]
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # Проверяем, что ключ был забанен
    deps["llm_client"].rotator.ban_key.assert_called_once_with("dead_key")


@pytest.mark.asyncio
async def test_react_no_tool_calls(mock_dependencies, mock_openai_response):
    """
    Тест: Если LLM затупила и ответила просто текстом (без вызова функций),
    цикл должен прерваться, чтобы не застрять.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    # Возвращаем ответ без tool_calls
    mock_session.chat.completions.create.return_value = mock_openai_response(
        "Я просто хочу поболтать.", finish_reason="stop"
    )
    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # Стейт должен вернуться в IDLE без ошибок и без вызова функций
    assert deps["agent_state"].state == AgentStatus.IDLE
    deps["sql_ticks"].save_tick.assert_not_called()


def test_react_inject_images_no_markers(mock_dependencies):
    """Тест: если маркеров нет, функция должна вернуть список без изменений."""
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    messages = [
        {"role": "tool", "content": "Обычный ответ тулзы"},
        {"role": "user", "content": "Контекст агента"},
    ]

    result = loop._inject_images_to_payload(messages.copy())

    assert result == messages
    # Контент user-сообщения остался строкой
    assert isinstance(result[-1]["content"], str)


def test_react_inject_images_success(mock_dependencies, tmp_path):
    """Тест: если есть маркер, функция читает картинку, кодирует в Base64 и меняет формат messages."""
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    # Создаем настоящую (но крошечную) фейковую картинку
    fake_img = tmp_path / "test.jpg"
    fake_img.write_bytes(b"hello")  # Base64 для 'hello' это 'aGVsbG8='

    # Имитируем историю, где на прошлом шаге тулза вернула маркер
    messages = [
        {"role": "tool", "content": f"Result: [SYSTEM_MARKER_IMAGE_ATTACHED: {fake_img.resolve()}]"},
        {"role": "user", "content": "Анализируй"},
    ]

    result = loop._inject_images_to_payload(messages.copy())

    last_msg_content = result[-1]["content"]

    # Проверяем, что строка превратилась в массив
    assert isinstance(last_msg_content, list)

    # Текст никуда не делся
    assert last_msg_content[0]["type"] == "text"
    assert last_msg_content[0]["text"] == "Анализируй"

    # Картинка подсосалась
    assert last_msg_content[1]["type"] == "image_url"
    assert "image/jpeg" in last_msg_content[1]["image_url"]["url"]
    assert "aGVsbG8=" in last_msg_content[1]["image_url"]["url"]  # Проверка кодировки


@pytest.mark.asyncio
async def test_react_timeout_retry(mock_dependencies, mock_openai_response):
    """
    Тест: Ошибка таймаута (240 сек). Цикл должен повторить запрос, не увеличивая шаг.
    """
    deps = mock_dependencies
    loop = ReactLoop(**deps)

    mock_session = AsyncMock()
    mock_session.api_key = "key_1"

    # Первая попытка - Timeout, вторая - успешный выход
    timeout_err = openai.APITimeoutError(request=MagicMock())
    mock_session.chat.completions.create.side_effect = [
        timeout_err,
        mock_openai_response('{"thoughts": "ok", "actions": []}'),
    ]

    deps["llm_client"].get_session = MagicMock(return_value=mock_session)

    await loop.run("TEST", {}, missed_events=[])

    # Проверяем, что LLM вызывалась 2 раза
    assert mock_session.chat.completions.create.call_count == 2
    # Шаг должен остаться 1, потому что первая попытка упала с таймаутом (шаг не "сгорел")
    assert deps["agent_state"].current_step == 1
    assert deps["agent_state"].state == AgentStatus.IDLE

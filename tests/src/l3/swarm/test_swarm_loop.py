import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.l3_agent.swarm.loop import SubagentLoop
from src.l3_agent.swarm.roles import Subagents


@pytest.fixture
def mock_loop_deps():
    llm = MagicMock()
    tracker = MagicMock()
    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "System Prompt"
    context_builder = MagicMock()
    context_builder.build.return_value = "Context"

    return {
        "subagent_id": "123",
        "role": Subagents.CODER,  # Передаем объект
        "task_description": "Task",
        "llm_client": llm,
        "model_name": "test-model",
        "prompt_builder": prompt_builder,
        "context_builder": context_builder,
        "allowed_skills": ["Allowed.tool"],
        "token_tracker": tracker,
        "max_steps": 3,
    }


@pytest.mark.asyncio
async def test_subagent_graceful_exit(mock_loop_deps, mock_openai_response):
    loop = SubagentLoop(**mock_loop_deps)

    # Имитируем, что субагент уже отправил отчет на предыдущем шаге
    loop.report_submitted = True

    mock_session = AsyncMock()
    mock_session.chat.completions.create.return_value = mock_openai_response(
        '{"thoughts": "Я всё сделал", "actions": []}'
    )
    loop.llm.get_session.return_value = mock_session

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is True
    assert len(loop.history) == 0


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.loop.call_skill", new_callable=AsyncMock)
async def test_subagent_forbidden_skill(mock_call_skill, mock_loop_deps, mock_openai_response):
    loop = SubagentLoop(**mock_loop_deps)
    loop.report_submitted = True  # Чтобы разрешить выход на втором шаге

    mock_session = AsyncMock()
    mock_session.chat.completions.create.side_effect = [
        mock_openai_response(
            '{"thoughts": "Hacking", "actions": [{"tool_name": "Forbidden.tool", "parameters": {}}]}'
        ),
        mock_openai_response('{"thoughts": "Exit", "actions": []}'),
    ]
    loop.llm.get_session.return_value = mock_session

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is True
    assert len(loop.history) == 1
    assert "Отказано в доступе" in loop.history[0]["results"]
    mock_call_skill.assert_not_called()


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.loop.call_skill", new_callable=AsyncMock)
async def test_subagent_invalid_json(mock_call_skill, mock_loop_deps, mock_openai_response):
    loop = SubagentLoop(**mock_loop_deps)
    loop.report_submitted = True

    mock_session = AsyncMock()
    mock_session.chat.completions.create.side_effect = [
        mock_openai_response("This is plain text, not JSON!"),
        mock_openai_response('{"thoughts": "Fixing", "actions": []}'),
    ]
    loop.llm.get_session.return_value = mock_session

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is True
    assert len(loop.history) == 1
    assert "Invalid JSON format" in loop.history[0]["results"]


@pytest.mark.asyncio
async def test_subagent_forces_report_submission(mock_loop_deps, mock_openai_response):
    """Тест: Если субагент пытается завершить работу без отправки отчета, система блокирует его."""
    loop = SubagentLoop(**mock_loop_deps)
    loop.max_steps = 2
    loop.report_submitted = False  # Отчет НЕ отправлен

    mock_session = AsyncMock()
    # LLM дважды настойчиво пытается выйти (пустой массив)
    mock_session.chat.completions.create.side_effect = [
        mock_openai_response('{"thoughts": "Я хочу уйти", "actions": []}'),
        mock_openai_response('{"thoughts": "Ну выпусти", "actions": []}'),
    ]
    loop.llm.get_session.return_value = mock_session

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    # Агент НЕ должен был завершиться штатно, его убьет по max_steps
    assert loop.is_done is False
    assert len(loop.history) == 2

    # Убеждаемся, что система наложила вето
    assert "[System Error]" in loop.history[0]["results"]
    assert "Это запрещено." in loop.history[0]["results"]


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.loop.call_skill", new_callable=AsyncMock)
async def test_subagent_llm_crash_forces_report(mock_call_skill, mock_loop_deps):
    """Тест: Если LLM субагента падает с критической ошибкой (404/Timeout), он шлет краш-репорт."""
    loop = SubagentLoop(**mock_loop_deps)

    # Мокаем критическое падение LLM
    loop._call_llm_with_retries = AsyncMock(return_value=None)

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    # Убеждаемся, что цикл вызвал инструмент отправки отчета
    mock_call_skill.assert_called_once()
    args = mock_call_skill.call_args[0]

    assert args[0] == "SubagentReport.submit_final_report"
    assert "Сбой инициализации" in args[1]["report"]
    assert "Модель недоступна" in args[1]["report"]


@pytest.mark.asyncio
@patch("src.l3_agent.swarm.loop.call_skill", new_callable=AsyncMock)
async def test_subagent_timeout_forces_report(
    mock_call_skill, mock_loop_deps, mock_openai_response
):
    """Тест: Если субагент зациклился и достиг max_steps, он принудительно шлет краш-репорт."""
    loop = SubagentLoop(**mock_loop_deps)
    loop.max_steps = 1

    mock_session = AsyncMock()
    # Агент возвращает разрешенное действие (Allowed.tool), но не отправляет отчет
    mock_session.chat.completions.create.return_value = mock_openai_response(
        '{"thoughts": "Working", "actions": [{"tool_name": "Allowed.tool", "parameters": {}}]}'
    )
    loop.llm.get_session.return_value = mock_session

    with patch.object(loop, "_dump_context_to_file"):
        await loop.run()

    assert loop.is_done is False

    # 2 вызова: 1-й это Allowed.tool из ответа модели, 2-й это принудительный submit_final_report
    assert mock_call_skill.call_count == 2

    forced_call = mock_call_skill.call_args_list[-1]
    assert forced_call[0][0] == "SubagentReport.submit_final_report"
    assert "Timeout Error" in forced_call[0][1]["report"]


@pytest.mark.asyncio
async def test_subagent_dump_context_to_file(mock_loop_deps, tmp_path):
    loop = SubagentLoop(**mock_loop_deps)
    messages = [{"role": "system", "content": "Hello"}]

    with patch("src.l3_agent.swarm.loop.Path") as mock_path_class:
        mock_dir = MagicMock()
        mock_path_class.return_value = mock_dir
        mock_dir.__truediv__.return_value = tmp_path / "last_prompt.md"

        loop._dump_context_to_file(messages, current_step=1)

        content = (tmp_path / "last_prompt.md").read_text(encoding="utf-8")
        assert "SUBAGENT DUMP" in content
        assert "**Role**: SOFTWARE ENGINEER" in content  # Имя из объекта
        assert "Hello" in content

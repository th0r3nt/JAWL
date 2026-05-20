import pytest
import openai
from unittest.mock import MagicMock, AsyncMock, patch

from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.llm.exceptions import AllKeysExhaustedError


@pytest.fixture
def mock_executor_deps():
    llm = MagicMock()
    llm.rotator = MagicMock()
    tracker = MagicMock()
    return llm, tracker


@pytest.mark.asyncio
async def test_executor_success(mock_executor_deps):
    llm, tracker = mock_executor_deps
    mock_session = AsyncMock()
    llm.get_session.return_value = mock_session

    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Success Content"
    mock_session.chat.completions.create.return_value = mock_response

    executor = LLMExecutor(llm, tracker)
    res = await executor.execute("test-model", [], 0.7, MagicMock(), "[Log]")

    assert res == "Success Content"
    tracker.add_output_record.assert_called_once()


@pytest.mark.asyncio
@patch("src.l3_agent.llm.executor.asyncio.sleep", new_callable=AsyncMock)
async def test_executor_rate_limit(mock_sleep, mock_executor_deps):
    """Тест: Executor ловит 429, отправляет ключ в кулдаун и успешно ретраит."""
    llm, tracker = mock_executor_deps

    mock_session1 = AsyncMock()
    mock_session1.api_key = "key1"

    mock_resp = MagicMock()
    mock_resp.headers = {"retry-after": "5"}
    rate_error = openai.RateLimitError("429", response=mock_resp, body={})

    mock_session2 = AsyncMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].message.content = "Finally Success"
    mock_session2.chat.completions.create.return_value = mock_response

    # Первый вызов падает с 429, второй (новый ключ из ротатора) проходит
    llm.get_session.side_effect = [mock_session1, mock_session2]
    mock_session1.chat.completions.create.side_effect = rate_error

    executor = LLMExecutor(llm, tracker)
    res = await executor.execute("model", [], 0.7, MagicMock(), "[Log]")

    assert res == "Finally Success"
    llm.rotator.cooldown_key.assert_called_once_with("key1", 5)


@pytest.mark.asyncio
async def test_executor_auth_error_bans_key(mock_executor_deps):
    """Тест: Executor ловит 401 и банит мертвый ключ навсегда."""
    llm, tracker = mock_executor_deps

    mock_session = AsyncMock()
    mock_session.api_key = "dead_key"
    auth_err = openai.AuthenticationError("401", response=MagicMock(), body={})

    mock_session.chat.completions.create.side_effect = [
        auth_err,
        MagicMock(choices=[MagicMock(message=MagicMock(tool_calls=None, content="OK"))]),
    ]
    llm.get_session.return_value = mock_session

    executor = LLMExecutor(llm, tracker)
    await executor.execute("model", [], 0.7, MagicMock(), "[Log]")

    llm.rotator.ban_key.assert_called_once_with("dead_key")


@pytest.mark.asyncio
@patch("src.l3_agent.llm.executor.asyncio.sleep", new_callable=AsyncMock)
async def test_executor_all_keys_exhausted(mock_sleep, mock_executor_deps):
    """Тест: Ротатор сообщает, что все в кулдауне. Executor спит и ретраит."""
    llm, tracker = mock_executor_deps

    # 1. Первый раз get_session падает, т.к. все ключи заблочены
    # 2. Второй раз возвращает сессию, которая проходит успешно
    llm.get_session.side_effect = [
        AllKeysExhaustedError(wait_time=10),
        AsyncMock(
            chat=MagicMock(
                completions=MagicMock(
                    create=AsyncMock(
                        return_value=MagicMock(
                            choices=[
                                MagicMock(message=MagicMock(tool_calls=None, content="OK"))
                            ]
                        )
                    )
                )
            )
        ),
    ]

    executor = LLMExecutor(llm, tracker)
    res = await executor.execute("model", [], 0.7, MagicMock(), "[Log]")

    assert res == "OK"
    mock_sleep.assert_called_once_with(11)  # wait_time + 1

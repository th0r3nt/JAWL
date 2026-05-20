import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.settings import HostTerminalConfig
from src.l0_state.agent.state import AgentState

from src.l2_interfaces.host.terminal.state import HostTerminalState
from src.l2_interfaces.host.terminal.client import HostTerminalClient
from src.l2_interfaces.host.terminal.events import HostTerminalEvents
from src.l2_interfaces.host.terminal.skills.messages import HostTerminalMessages

from src.l3_agent.heartbeat import Heartbeat
from src.l3_agent.react.loop import ReactLoop
from src.l3_agent.skills.registry import register_instance, clear_registry


@pytest.mark.asyncio
async def test_e2e_terminal_to_react_loop(tmp_path: Path):
    """
    Хардкорный E2E тест полного цикла общения:
    TCP Сокет -> Воркер -> EventBus -> Heartbeat -> ReactLoop -> Скилл -> TCP Сокет.
    """
    clear_registry()

    # 1. ПОДГОТОВКА ИНФРАСТРУКТУРЫ
    bus = EventBus()
    state = HostTerminalState()
    config = HostTerminalConfig(enabled=True)

    # Поднимаем реальный TCP сервер терминала
    client = HostTerminalClient(
        state=state,
        config=config,
        data_dir=tmp_path,
        agent_name="V.E.G.A.",
        timezone=3,
    )
    await client.start()

    events = HostTerminalEvents(client, bus)
    await events.start()

    # Регистрируем навык отправки сообщений
    terminal_skills = HostTerminalMessages(client)
    register_instance(terminal_skills)

    # 2. МОКАЕМ ЯДРО АГЕНТА
    agent_state = AgentState(max_react_steps=1)  # noqa: F841

    mock_react_loop = MagicMock(spec=ReactLoop)
    mock_react_loop.run = AsyncMock()

    # Наш фейковый ReAct-цикл: когда его будят, он "думает" и вызывает скилл ответа
    async def fake_react_run(event_name, payload, missed_events):
        from src.l3_agent.skills.registry import execute_skill
        from src.l3_agent.skills.schema import ActionCall

        # Эмулируем, что LLM решила ответить пользователю
        actions = [
            ActionCall(
                tool_name="HostTerminalMessages.send_message_to_terminal",
                parameters={"text": "Привет, кожаный мешок!"},
            )
        ]
        await execute_skill(actions)

    mock_react_loop.run.side_effect = fake_react_run

    # Поднимаем Heartbeat, который слушает шину
    hb = Heartbeat(
        react_loop=mock_react_loop,
        heartbeat_interval=3600,  # Спит час
        continuous_cycle=False,
        accel_config=MagicMock(critical_multiplier=0.0),  # Моментальное пробуждение
        timezone=3,
    )

    # Ручная подписка моста (имитируем EventBridge)
    async def hb_handler(**kwargs):
        hb.answer_to_event(
            Events.HOST_TERMINAL_MESSAGE.level, Events.HOST_TERMINAL_MESSAGE.name, kwargs
        )

    bus.subscribe(Events.HOST_TERMINAL_MESSAGE, hb_handler)

    # Запускаем Heartbeat в фоне
    hb_task = asyncio.create_task(hb.start())
    await asyncio.sleep(0.1)  # Даем ему уснуть

    # 3. ЭМУЛЯЦИЯ ПОЛЬЗОВАТЕЛЯ (Подключаемся к TCP-сокету)
    actual_port = int(client.port_file.read_text())
    reader, writer = await asyncio.open_connection("127.0.0.1", actual_port)

    # Handshake
    writer.write(b"JAWL_HANDSHAKE\n")
    await writer.drain()

    # Отправляем сообщение от юзера в формате JSON-Lines
    user_payload = json.dumps({"text": "Проснись!"}) + "\n"
    writer.write(user_payload.encode("utf-8"))
    await writer.drain()

    # Даем системе время прожевать байты -> ивенты -> хартбит -> реакт -> скилл
    await asyncio.sleep(0.5)

    # Читаем ответ от агента из сокета
    response_bytes = await reader.readline()
    response_str = response_bytes.decode("utf-8")

    # 4. ПРОВЕРКИ (ASSERTS)

    # Агент должен был получить сообщение и ответить
    assert "Привет, кожаный мешок!" in response_str

    # Проверяем, что ReAct цикл реально был вызван правильным триггером
    mock_react_loop.run.assert_called_once()
    call_kwargs = mock_react_loop.run.call_args[1]
    assert call_kwargs["event_name"] == "HOST_TERMINAL_MESSAGE"
    assert call_kwargs["payload"]["message"] == "Проснись!"

    # Проверяем L0 State
    assert "Проснись!" in state.recent_messages[-2]
    assert "Привет, кожаный мешок!" in state.recent_messages[-1]

    # 5. ОЧИСТКА (TEARDOWN)
    writer.close()
    await writer.wait_closed()
    await events.stop()
    await client.stop()
    hb.stop()
    await hb_task

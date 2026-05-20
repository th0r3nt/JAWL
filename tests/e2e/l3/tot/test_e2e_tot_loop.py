import pytest
from unittest.mock import AsyncMock, MagicMock

from src.utils.settings import TreeOfThoughtsConfig

from src.l0_state.agent.state import AgentState

from src.l3_agent.react.loop import ReactLoop

from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.context.builder import ContextBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.tot.generator import ToTGenerator


@pytest.mark.asyncio
async def test_e2e_react_loop_with_tot_auto():
    """
    E2E Тест: Проверка автоматической генерации Tree of Thoughts.
    Убеждаемся, что на 1-м шаге ReactLoop вызывает генератор,
    а затем главный контекст пополняется сгенерированным деревом.
    """

    agent_state = AgentState(max_react_steps=2)
    registry = ContextRegistry()

    context_builder = ContextBuilder(agent_state, registry)

    async def fake_tot_provider(**kwargs):
        return agent_state.current_thoughts_tree

    registry.register_provider(
        "tree_of_thoughts", fake_tot_provider, section=ContextSection.TREE_OF_THOUGHTS
    )

    mock_tot_generator = MagicMock(spec=ToTGenerator)
    mock_tot_generator.generate = AsyncMock(
        return_value="## TREE OF THOUGHTS\n**Ветка: Тестовая стратегия**"
    )

    # Обновляем конфиг под новую геометрию (хотя в E2E тесте это мокается,
    # лучше передавать правильный класс)
    tot_config = TreeOfThoughtsConfig(
        enabled=True,
        mode="auto",
        auto_interval_steps=3,
        branches=2,
        simulations_per_branch=2,
        max_depth=2,
    )

    mock_main_llm = MagicMock()
    mock_main_session = AsyncMock()

    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = '{"reflection": "Я вижу дерево мыслей!", "actions": []}'
    mock_main_session.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=mock_msg)]
    )
    mock_main_llm.get_session.return_value = mock_main_session

    mock_sql_ticks = MagicMock()
    mock_sql_ticks.save_tick = AsyncMock()

    mock_bus = MagicMock()
    mock_bus.publish = AsyncMock()

    llm_executor = LLMExecutor(mock_main_llm, MagicMock())
    loop = ReactLoop(
        executor=llm_executor,
        prompt_builder=MagicMock(),
        context_builder=context_builder,
        agent_state=agent_state,
        sql_ticks=mock_sql_ticks,
        vector_manager=MagicMock(),
        tools=[],
        event_bus=mock_bus,
        tot_config=tot_config,
        tot_generator=mock_tot_generator,
    )

    # Выполнение
    await loop.run(
        event_name="USER_REQUEST", payload={"message": "Реши сложную задачу"}, missed_events=[]
    )

    # Проверки
    mock_tot_generator.generate.assert_called_once()
    assert "Ветка: Тестовая стратегия" in agent_state.current_thoughts_tree

    call_args = mock_main_session.chat.completions.create.call_args[1]
    messages_to_llm = call_args["messages"]
    user_context = messages_to_llm[1]["content"]

    assert "TREE OF THOUGHTS" in user_context
    assert "Ветка: Тестовая стратегия" in user_context

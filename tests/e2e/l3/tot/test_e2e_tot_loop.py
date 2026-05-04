import pytest
from unittest.mock import AsyncMock, MagicMock

from src.l0_state.agent.state import AgentState
from src.l3_agent.react.loop import ReactLoop
from src.utils.settings import TreeOfThoughtsConfig
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

    # 1. Настраиваем стейт и реестр
    agent_state = AgentState(max_react_steps=2)
    registry = ContextRegistry()

    # 2. Настраиваем ContextBuilder
    context_builder = ContextBuilder(agent_state, registry)

    # Имитируем регистрацию ToT-провайдера (которую делает SystemBuilder)
    async def fake_tot_provider(**kwargs):
        return agent_state.current_thoughts_tree

    registry.register_provider(
        "tree_of_thoughts", fake_tot_provider, section=ContextSection.TREE_OF_THOUGHTS
    )

    # 3. Мокаем ToTGenerator (Подсознание)
    mock_tot_generator = MagicMock(spec=ToTGenerator)
    # Подсознание генерирует классный план (ВАЖНО: это должен быть AsyncMock, так как мы его await-им)
    mock_tot_generator.generate = AsyncMock(
        return_value="## TREE OF THOUGHTS\n**Ветка: Тестовая стратегия**"
    )

    # 4. Настраиваем конфигурацию
    tot_config = TreeOfThoughtsConfig(enabled=True, mode="auto", auto_interval_steps=3)

    # 5. Мокаем Главную Модель (Оркестратора)
    mock_main_llm = MagicMock()
    mock_main_session = AsyncMock()

    # Главная модель возвращает пустой массив actions (чтобы цикл сразу завершился)
    mock_msg = MagicMock()
    mock_msg.tool_calls = None
    mock_msg.content = '{"thoughts": "Я вижу дерево мыслей!", "actions": []}'
    mock_main_session.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(message=mock_msg)]
    )
    mock_main_llm.get_session.return_value = mock_main_session

    # --- ИСПРАВЛЕНИЕ ЗДЕСЬ: Мокаем БД корректно, чтобы await save_tick не падал ---
    mock_sql_ticks = MagicMock()
    mock_sql_ticks.save_tick = AsyncMock()
    # -----------------------------------------------------------------------------

    # 6. Инициализируем ReactLoop
    loop = ReactLoop(
        llm_client=mock_main_llm,
        prompt_builder=MagicMock(),
        context_builder=context_builder,
        agent_state=agent_state,
        sql_ticks=mock_sql_ticks,  # <- Передаем правильный мок
        vector_manager=MagicMock(),
        token_tracker=MagicMock(),
        tools=[],
        tot_config=tot_config,
        tot_generator=mock_tot_generator,
    )

    # ==============================
    # ⚡ ВЫПОЛНЕНИЕ
    # ==============================
    await loop.run(
        event_name="USER_REQUEST", payload={"message": "Реши сложную задачу"}, missed_events=[]
    )

    # ==============================
    # 🎯 ПРОВЕРКИ
    # ==============================
    # 1. Генератор подсознания ДОЛЖЕН был вызваться 1 раз (т.к. мы на 1-м шаге)
    mock_tot_generator.generate.assert_called_once()

    # 2. Дерево мыслей должно было попасть в кэш агента
    assert "Ветка: Тестовая стратегия" in agent_state.current_thoughts_tree

    # 3. Главная LLM ДОЛЖНА была получить "ДЕРЕВО МЫСЛЕЙ" в своем промпте
    # Проверяем аргументы, которые ушли в openai.chat.completions.create
    call_args = mock_main_session.chat.completions.create.call_args[1]
    messages_to_llm = call_args["messages"]

    # messages_to_llm[1] - это user контекст
    user_context = messages_to_llm[1]["content"]
    assert "TREE OF THOUGHTS" in user_context
    assert "Ветка: Тестовая стратегия" in user_context

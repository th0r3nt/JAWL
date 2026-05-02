import pytest
import asyncio


@pytest.mark.asyncio
async def test_save_and_get_ticks(ticks_manager):
    # Симулируем 3 тика агента
    for i in range(3):
        await ticks_manager.save_tick(
            thoughts=f"Мысль {i}",
            actions=[{"tool_name": "test", "parameters": {}}],
            results={"test": "ok"},
        )
        await asyncio.sleep(0.01)

    # Получаем последние 2
    last_ticks = await ticks_manager.get_ticks(limit=2)

    assert len(last_ticks) == 2
    # Поскольку они возвращаются в хронологическом порядке (сначала старые, потом новые),
    # последние 2 из [0, 1, 2] — это 1 и 2.
    assert last_ticks[0].thoughts == "Мысль 1"
    assert last_ticks[1].thoughts == "Мысль 2"

    # Проверяем JSON структуру
    assert last_ticks[1].actions[0]["tool_name"] == "test"
    assert last_ticks[1].results["test"] == "ok"

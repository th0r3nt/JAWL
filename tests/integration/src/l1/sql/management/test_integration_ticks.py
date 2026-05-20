import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from src.utils.dtime import format_datetime


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


@pytest.mark.asyncio
async def test_get_ticks_by_time(ticks_manager):
    """Тест: Фильтрация логов по времени и форматирование (detail=True/False)."""

    id_1 = await ticks_manager.save_tick("Мысль 1 (Старая)", [], {})  # noqa: F841
    await asyncio.sleep(1.1)
    
    # Фиксируем окно СТРОГО вокруг второго тика
    start_dt = datetime.now(timezone.utc)
    
    id_2 = await ticks_manager.save_tick(  # noqa: F841
        "Мысль 2 (Целевая)", [{"tool_name": "test", "parameters": {}}], {"status": "ok"}
    )
    
    # Делаем запас в 1 секунду вперед, чтобы строка формата точно захватила этот тик
    end_dt = datetime.now(timezone.utc) + timedelta(seconds=1)
    
    await asyncio.sleep(1.1)
    id_3 = await ticks_manager.save_tick("Мысль 3 (Будущая)", [], {})  # noqa: F841

    start_str = format_datetime(start_dt, ticks_manager.tz_offset, "%Y-%m-%d %H:%M:%S")
    end_str = format_datetime(end_dt, ticks_manager.tz_offset, "%Y-%m-%d %H:%M:%S")

    res_short = await ticks_manager.get_ticks_by_time(start_str, end_str, detail=False)
    assert res_short.is_success is True
    assert "Мысль 2 (Целевая)" in res_short.message
    assert "Мысль 1" not in res_short.message
    assert "Мысль 3" not in res_short.message
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from src.l1_databases.sql.tables import DriveTable, TickTable


@pytest.mark.asyncio
async def test_drives_downtime_compensation(drives_manager, ticks_manager):
    """
    Интеграционный тест: Механизм компенсации даунтайма (pause_on_offline).
    Агент был выключен 10 часов. При включении он должен "перемотать" таймеры мотиваторов,
    чтобы не проснуться с 100% дефицитом.
    """
    await drives_manager.bootstrap_fundamental_drives()

    # 1. Задаем исходную точку (10 часов назад)
    past_time = datetime.now(timezone.utc) - timedelta(hours=48)

    async with drives_manager.db.session_factory() as session:
        # Устанавливаем время драйвов на 10 часов назад (якобы они были сыты тогда)
        result = await session.execute(select(DriveTable))
        for d in result.scalars().all():
            d.last_satisfied_at = past_time

        # Симулируем, что последний "тик" (вздох) агента тоже был 10 часов назад
        fake_tick = TickTable(
            id="fake_tick_1",
            created_at=past_time,
            thoughts="Ухожу в сон...",
            actions=[],
            results={},
        )
        session.add(fake_tick)
        await session.commit()

    # 2. Вычисляем дефицит ДО компенсации (должен быть огромным)
    context_before = await drives_manager.get_context_block()
    assert (
        "Deficit: 100%" in context_before or "Deficit: 8" in context_before
    )  # 80-100% в зависимости от dynamic_reduction

    # 3. Вызываем механизм компенсации (вызывается в SQLManager.connect)
    await drives_manager.adjust_downtime()

    # 4. Проверяем результат ПОСЛЕ компенсации
    context_after = await drives_manager.get_context_block()

    # Дефицит должен откатиться почти до нуля (потому что таймеры сдвинулись вперед на 10 часов)
    assert "Deficit: 0%" in context_after or "Deficit: 1%" in context_after

    # Проверяем физически в БД
    async with drives_manager.db.session_factory() as session:
        result = await session.execute(
            select(DriveTable).where(DriveTable.name == "Curiosity")
        )
        drive = result.scalar_one()

        # Таймер удовлетворения должен быть сдвинут почти к текущему моменту (now)
        delta = datetime.now(timezone.utc) - drive.last_satisfied_at.replace(
            tzinfo=timezone.utc
        )
        assert delta.total_seconds() < 60  # Погрешность выполнения теста


@pytest.mark.asyncio
async def test_drives_downtime_compensation_disabled(drives_manager, ticks_manager):
    """
    Тест: Если pause_on_offline = False, агент честно страдает от даунтайма.
    """
    drives_manager.pause_on_offline = False
    await drives_manager.bootstrap_fundamental_drives()

    past_time = datetime.now(timezone.utc) - timedelta(hours=48)

    async with drives_manager.db.session_factory() as session:
        result = await session.execute(select(DriveTable))
        for d in result.scalars().all():
            d.last_satisfied_at = past_time

        fake_tick = TickTable(
            id="fake_tick_2", created_at=past_time, thoughts="Сплю...", actions=[], results={}
        )
        session.add(fake_tick)
        await session.commit()

    # Пытаемся компенсировать
    await drives_manager.adjust_downtime()

    # Страдания не должны прекратиться
    context_after = await drives_manager.get_context_block()
    assert "Deficit: 100%" in context_after or "Deficit: 8" in context_after

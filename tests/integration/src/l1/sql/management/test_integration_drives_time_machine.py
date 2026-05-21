import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from sqlalchemy import select

from src.l1_databases.sql.tables import DriveTable, TickTable


@pytest.mark.asyncio
async def test_drives_downtime_compensation(drives_manager, ticks_manager):
    """
    Интеграционный тест: Механизм компенсации даунтайма (pause_on_offline).
    Проверяет резервный путь (fallback) через TickTable, если метаданные отсутствуют.
    """
    await drives_manager.bootstrap_fundamental_drives()

    # 1. Задаем исходную точку (48 часов назад)
    past_time = datetime.now(timezone.utc) - timedelta(hours=48)

    async with drives_manager.db.session_factory() as session:
        # Устанавливаем время драйвов на 48 часов назад (якобы они были сыты тогда)
        result = await session.execute(select(DriveTable))
        for d in result.scalars().all():
            d.last_satisfied_at = past_time

        # Симулируем, что последний "тик" (вздох) агента тоже был 48 часов назад
        fake_tick = TickTable(
            id="fake_tick_1",
            created_at=past_time,
            thoughts="Ухожу в сон...",
            actions=[],
            results={},
        )
        session.add(fake_tick)
        await session.commit()

    # Принудительно отключаем чтение реального файла метаданных с диска разработчика,
    # заставляя систему использовать резервный механизм БД (TickTable)
    with patch(
        "src.l1_databases.sql.management.drives.crud.get_last_active_time", return_value=None
    ):
        # 2. Вычисляем дефицит ДО компенсации (должен быть огромным)
        context_before = await drives_manager.get_context_block()
        assert (
            "Deficit: 100%" in context_before or "Deficit: 8" in context_before
        )  # 80-100% в зависимости от dynamic_reduction

        # 3. Вызываем механизм компенсации (вызывается в SQLManager.connect)
        await drives_manager.adjust_downtime()

        # 4. Проверяем результат ПОСЛЕ компенсации
        context_after = await drives_manager.get_context_block()

        # Дефицит должен откатиться почти до нуля (потому что таймеры сдвинулись вперед на 48 часов)
        assert "Deficit: 0%" in context_after or "Deficit: 1%" in context_after


@pytest.mark.asyncio
async def test_drives_downtime_compensation_via_metadata(drives_manager):
    """
    Интеграционный тест: Проверка приоритетного пути компенсации через метаданные system_meta.json.
    """
    await drives_manager.bootstrap_fundamental_drives()

    # Задаем исходную точку (48 часов назад)
    past_time = datetime.now(timezone.utc) - timedelta(hours=48)

    async with drives_manager.db.session_factory() as session:
        result = await session.execute(select(DriveTable))
        for d in result.scalars().all():
            d.last_satisfied_at = past_time
        await session.commit()

    # Имитируем, что файл метаданных содержит время активности ровно 48 часов назад
    with patch(
        "src.l1_databases.sql.management.drives.crud.get_last_active_time",
        return_value=past_time.timestamp(),
    ):
        # Вычисляем дефицит ДО компенсации
        context_before = await drives_manager.get_context_block()
        assert "Deficit: 100%" in context_before or "Deficit: 8" in context_before

        # Вызываем механизм компенсации
        await drives_manager.adjust_downtime()

        # Проверяем результат ПОСЛЕ компенсации
        context_after = await drives_manager.get_context_block()
        assert "Deficit: 0%" in context_after or "Deficit: 1%" in context_after


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

    with patch(
        "src.l1_databases.sql.management.drives.crud.get_last_active_time", return_value=None
    ):
        # Пытаемся компенсировать
        await drives_manager.adjust_downtime()

        # Страдания не должны прекратиться
        context_after = await drives_manager.get_context_block()
        assert "Deficit: 100%" in context_after or "Deficit: 8" in context_after

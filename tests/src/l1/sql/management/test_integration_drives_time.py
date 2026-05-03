import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.mark.asyncio
async def test_integration_drives_time_decay_to_critical(drives_manager):
    """
    Интеграционный тест: "Время идет -> Дефицит растет -> Контекст предупреждает LLM".
    Имитирует длительный сон агента и проверяет, что математика Мотиваторов
    конвертируется в алерты "Критический дефицит" для промпта.
    """

    # 1. Загружаем драйвы
    await drives_manager.bootstrap_fundamental_drives()

    # Проверяем стартовый статус
    start_context = await drives_manager.get_context_block()
    assert "Дефицит: 0/100" in start_context
    assert "(В норме:" in start_context

    # 2. Машина времени: переносимся на 6 часов вперед
    # decay_interval = 3600 (1 час). decay_rate = 5.0 (5% в час).
    # За 6 часов дефицит должен вырасти до 30%.

    future_time_1 = datetime.now(timezone.utc) + timedelta(hours=6)

    with patch("src.l1_databases.sql.management.drives.datetime") as mock_dt:
        mock_dt.now.return_value = future_time_1

        mid_context = await drives_manager.get_context_block()
        assert "Дефицит: 30/100" in mid_context
        assert "(Лёгкий дефицит:" in mid_context

    # 3. Машина времени: переносимся на 20 часов вперед (Итого: 100%)
    future_time_2 = datetime.now(timezone.utc) + timedelta(hours=20)

    with patch("src.l1_databases.sql.management.drives.datetime") as mock_dt:
        mock_dt.now.return_value = future_time_2

        crit_context = await drives_manager.get_context_block()
        assert "Дефицит: 100/100" in crit_context
        assert "(Критический дефицит: приоритетная задача)" in crit_context

    # 4. Агент решает удовлетворить драйв на 40% (в моменте future_time_2)
    with patch("src.l1_databases.sql.management.drives.datetime") as mock_dt:
        mock_dt.now.return_value = future_time_2

        await drives_manager.satisfy_drive("Curiosity", 40, "Прочитал Хабр")

        # Дефицит был 100, стал 60. Статус должен измениться.
        final_context = await drives_manager.get_context_block()
        assert "Дефицит: 60/100" in final_context
        assert "(Растет:" in final_context
        assert "Прочитал Хабр" in final_context

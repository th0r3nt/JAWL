import pytest


@pytest.mark.asyncio
async def test_drives_bootstrap_and_context(drives_manager):
    """Тест: Базовые драйвы успешно создаются при первом запуске."""

    await drives_manager.bootstrap_fundamental_drives()

    context = await drives_manager.get_context_block()
    assert "Curiosity" in context
    assert "Social" in context
    assert "Mastery" in context
    assert "Deficit: " in context


@pytest.mark.asyncio
async def test_drives_satisfy_drive(drives_manager):
    """Тест: частичное удовлетворение драйва обновляет рефлексию и историю."""

    await drives_manager.bootstrap_fundamental_drives()

    # Агент удовлетворил любопытство на 50%
    res = await drives_manager.satisfy_drive(
        drive_name="curiosity",
        amount=50,
        reflection_summary="Прочитала статью на Хабре про вектора.",
    )
    assert res.is_success is True
    assert res.message == "True"

    context = await drives_manager.get_context_block()
    assert "Прочитала статью на Хабре про вектора." in context
    assert "Снижен на 50%:" in context


@pytest.mark.asyncio
async def test_drives_custom_crud_and_limits(drives_manager):
    """Тест: Создание кастомного драйва, лимиты и удаление."""

    res_1 = await drives_manager.create_custom_drive("Мониторинг логов", "Чек ошибок")
    res_2 = await drives_manager.create_custom_drive("Проверка почты", "Чек писем")

    assert res_1.is_success is True
    assert res_2.is_success is True

    res_fail = await drives_manager.create_custom_drive("Лишний", "Не влезет")
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message

    res_del = await drives_manager.delete_custom_drive("Мониторинг логов")
    assert res_del.is_success is True


@pytest.mark.asyncio
async def test_drives_cannot_delete_fundamental(drives_manager):
    """Тест: Система защищает базовые драйвы от удаления агентом."""

    await drives_manager.bootstrap_fundamental_drives()

    res_del = await drives_manager.delete_custom_drive("Social")
    assert res_del.is_success is False
    assert "Базовые (Fundamental) драйвы нельзя удалить" in res_del.message


@pytest.mark.asyncio
async def test_drives_semantic_matrix_escalation(drives_manager):
    """
    Интеграционный тест: Эскалация семантического состояния при росте дефицита.
    Проверяет, как сухие проценты превращаются в текстовые ощущения (1-5 стадия).
    """
    await drives_manager.bootstrap_fundamental_drives()

    # 1. Сброс (Дефицит ~0%)
    await drives_manager.satisfy_drive("curiosity", 100, "Полный сброс")

    context_stage1 = await drives_manager.get_context_block()

    # Ищем фразу из 1-й стадии (Интеллектуальная пресыщенность)
    assert (
        "Intellectual satiety" in context_stage1
        or "Интеллектуальная пресыщенность" in context_stage1
    )

    # 2. Перематываем время на 10 интервалов вперед
    # В фикстуре decay_rate = 5.0, значит дефицит должен стать ~50% (3-я стадия)
    from datetime import datetime, timezone, timedelta

    async with drives_manager.db.session_factory() as session:
        from sqlalchemy import select
        from src.l1_databases.sql.tables import DriveTable

        result = await session.execute(
            select(DriveTable).where(DriveTable.name == "Curiosity")
        )
        drive = result.scalar_one()

        # Искусственно стареем драйв на 10 интервалов
        drive.last_satisfied_at = datetime.now(timezone.utc) - timedelta(
            seconds=drive.decay_interval_sec * 10
        )
        await session.commit()

    context_stage3 = await drives_manager.get_context_block()

    # Ищем фразу из 3-й стадии (Легкий информационный голод)
    assert (
        "Mild information hunger" in context_stage3
        or "Mild lack of external stimuli" in context_stage3
    )

    # 3. Доводим систему до максимума (Дефицит 100%)
    async with drives_manager.db.session_factory() as session:
        result = await session.execute(
            select(DriveTable).where(DriveTable.name == "Curiosity")
        )
        drive = result.scalar_one()
        drive.last_satisfied_at = datetime.now(timezone.utc) - timedelta(
            seconds=drive.decay_interval_sec * 50
        )
        await session.commit()

    context_stage5 = await drives_manager.get_context_block()

    # Ищем фразу из 5-й стадии (Информационная депривация)
    assert "Information deprivation" in context_stage5 or "Chaos" in context_stage5

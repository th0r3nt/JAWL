import pytest


@pytest.mark.asyncio
async def test_drives_bootstrap_and_context(drives_manager):
    """Тест: Базовые драйвы успешно создаются при первом запуске, дефицит считается корректно."""

    await drives_manager.bootstrap_fundamental_drives()

    context = await drives_manager.get_context_block()
    assert "Curiosity" in context
    assert "Social" in context
    assert "Mastery" in context
    assert "Дефицит: 0/100" in context


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
    assert "снижен на 50%" in res.message

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

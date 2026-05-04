import pytest


@pytest.mark.asyncio
async def test_add_and_get_traits(traits_manager):
    # Создаем черту
    res_add = await traits_manager.add_trait(
        name="Токсичность", description="Отвечать сарказмом на глупые вопросы", reason="Скука"
    )
    assert res_add.is_success is True
    assert "ID:" in res_add.message

    # Вытаскиваем ID
    trait_id = res_add.message.split("ID: ")[1].strip()

    # Проверяем получение
    res_get = await traits_manager.get_traits()
    assert res_get.is_success is True
    assert "Токсичность" in res_get.message
    assert "Скука" in res_get.message
    assert trait_id in res_get.message


@pytest.mark.asyncio
async def test_remove_trait(traits_manager):
    res_add = await traits_manager.add_trait("Любопытство", "Спрашивать детали")
    trait_id = res_add.message.split("ID: ")[1].strip()

    # Удаляем
    res_delete = await traits_manager.remove_trait(trait_id)
    assert res_delete.is_success is True

    # Проверяем, что список пуст
    res_get = await traits_manager.get_traits()
    assert "Список приобретенных черт личности пуст" in res_get.message


@pytest.mark.asyncio
async def test_add_trait_limit(traits_manager):
    await traits_manager.add_trait("Trait 1", "Desc")
    await traits_manager.add_trait("Trait 2", "Desc")

    # Третий должен упасть в лимит
    res_fail = await traits_manager.add_trait("Trait 3", "Desc")
    assert res_fail.is_success is False
    assert "Достигнут лимит" in res_fail.message

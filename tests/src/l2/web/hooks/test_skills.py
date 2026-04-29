import pytest
from src.l2_interfaces.web.hooks.skills.webhooks import WebHooksSkills


@pytest.mark.asyncio
async def test_read_webhook_payload_json(hooks_client):
    """Тест: Навык агента успешно читает JSON хук."""
    skill = WebHooksSkills(hooks_client)
    hooks_client.state.add_hook("123", "src", "12:00", {"user": "admin"}, "preview")

    res = await skill.read_webhook_payload("123")
    assert res.is_success is True
    assert "user" in res.message
    assert "admin" in res.message
    assert "```json" in res.message


@pytest.mark.asyncio
async def test_read_webhook_payload_text(hooks_client):
    """Тест: Навык агента успешно читает Text хук."""
    skill = WebHooksSkills(hooks_client)
    hooks_client.state.add_hook("456", "src", "12:00", "Plain text info", "preview")

    res = await skill.read_webhook_payload("456")
    assert res.is_success is True
    assert "Plain text info" in res.message
    assert "```text" in res.message


@pytest.mark.asyncio
async def test_read_webhook_payload_not_found(hooks_client):
    """Тест: Обработка запроса на несуществующий хук."""
    skill = WebHooksSkills(hooks_client)
    res = await skill.read_webhook_payload("999")

    assert res.is_success is False
    assert "не найден" in res.message


@pytest.mark.asyncio
async def test_clear_webhooks_history(hooks_client):
    """Тест: Навык полной очистки истории вебхуков."""
    skill = WebHooksSkills(hooks_client)

    # Заполняем стейт мусором
    hooks_client.state.add_hook("1", "src1", "12:00", {}, "prev1")
    hooks_client.state.add_hook("2", "src2", "12:01", {}, "prev2")
    assert len(hooks_client.state.recent_hooks) == 2

    res = await skill.clear_webhooks_history()

    assert res.is_success is True
    assert "Удалено 2 записей" in res.message
    assert len(hooks_client.state.recent_hooks) == 0
    assert len(hooks_client.state.preview_lines) == 0


@pytest.mark.asyncio
async def test_get_webhooks_by_source(hooks_client):
    """Тест: Фильтрация вебхуков по источнику."""
    skill = WebHooksSkills(hooks_client)

    # Добавляем разные источники
    hooks_client.state.add_hook("id_gh", "github", "12:00", {}, "GitHub Activity")
    hooks_client.state.add_hook("id_st", "stripe", "12:05", {}, "Stripe Payment")
    hooks_client.state.add_hook(
        "id_gh2", "GitHub", "12:10", {}, "Another GitHub"
    )  # Проверка case-insensitive

    # 1. Ищем существующий (регистр не важен)
    res = await skill.get_webhooks_by_source("GITHUB")
    assert res.is_success is True
    assert "Найдено 2 записей" in res.message
    assert "GitHub Activity" in res.message
    assert "Another GitHub" in res.message
    assert "Stripe" not in res.message

    # 2. Ищем несуществующий
    res_empty = await skill.get_webhooks_by_source("bitbucket")
    assert res_empty.is_success is True
    assert "не обнаружено" in res_empty.message

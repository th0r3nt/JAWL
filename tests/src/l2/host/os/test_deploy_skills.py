import pytest
from unittest.mock import AsyncMock, MagicMock
from src.l2_interfaces.host.os.skills.deploy import HostOSDeploy
from src.l2_interfaces.host.os.client import HostOSAccessLevel


@pytest.fixture
def deploy_skills(os_client):
    # Повышаем права доступа до OPERATOR (2), чтобы пройти проверку декоратора @require_access
    os_client.access_level = HostOSAccessLevel.OPERATOR

    # Мокаем deploy_manager внутри клиента
    os_client.deploy_manager = MagicMock()
    return HostOSDeploy(os_client)


@pytest.mark.asyncio
async def test_start_deploy_session_success(deploy_skills):
    """Тест: Успешный запуск сессии через навык."""
    # Настраиваем мок менеджера
    deploy_skills.host_os.deploy_manager.start_session.return_value = (True, "Сессия начата")

    res = await deploy_skills.start_deploy_session(reason="Fixing a bug")

    assert res.is_success is True
    assert "Сессия начата" in res.message
    deploy_skills.host_os.deploy_manager.start_session.assert_called_once()


@pytest.mark.asyncio
async def test_start_deploy_session_disabled_in_config(deploy_skills):
    """Тест: Если сессии не требуются (отключены в конфиге), возвращается заглушка."""
    deploy_skills.host_os.config.require_deploy_sessions = False

    res = await deploy_skills.start_deploy_session(reason="I want to")

    assert res.is_success is True
    assert "Деплой-сессии отключены в конфигурации" in res.message
    # Менеджер не должен был вызываться
    deploy_skills.host_os.deploy_manager.start_session.assert_not_called()


@pytest.mark.asyncio
async def test_commit_deploy_session(deploy_skills):
    """Тест: Агент вызывает коммит, и результат корректно транслируется."""
    # Имитируем успешное прохождение тестов
    deploy_skills.host_os.deploy_manager.commit_session = AsyncMock(
        return_value=(True, "Тесты пройдены")
    )

    res = await deploy_skills.commit_deploy_session()

    assert res.is_success is True
    assert "Тесты пройдены" in res.message
    deploy_skills.host_os.deploy_manager.commit_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_rollback_deploy_session(deploy_skills):
    """Тест: Навык принудительного отката сессии."""
    deploy_skills.host_os.deploy_manager.rollback_session.return_value = (
        True,
        "Откат выполнен",
    )

    res = await deploy_skills.rollback_deploy_session()

    assert res.is_success is True
    assert "Откат выполнен" in res.message
    deploy_skills.host_os.deploy_manager.rollback_session.assert_called_once()

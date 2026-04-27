from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSDeploy:
    """Навыки для безопасного изменения исходного кода самого агента."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    async def start_deploy_session(self, reason: str) -> SkillResult:
        """
        Открывает деплой-сессию.
        Необходимо для получения прав на изменение исходного кода файлов в папке src/.
        Сохраняет бекапы изменяемых файлов (Copy-on-Write).
        """

        if self.host_os.access_level < HostOSAccessLevel.OPERATOR:
            return SkillResult.fail(
                "Отказано в доступе. Требуется Access Level >= 2 (OPERATOR)."
            )

        if not self.host_os.config.require_deploy_sessions:
            return SkillResult.ok(
                "Деплой-сессии отключены в конфигурации. Возможность изменения кода напрямую по умолчанию включена."
            )

        success, msg = self.host_os.deploy_manager.start_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    async def commit_deploy_session(self) -> SkillResult:
        """
        Завершает деплой-сессию, прогоняя тесты (pytest) и синтаксис-чеки.
        Если тесты падают - код не откатывается, но дается попытки на исправление.
        При исчерпании попыток происходит автоматический Rollback.
        """

        if self.host_os.access_level < HostOSAccessLevel.OPERATOR:
            return SkillResult.fail("Отказано в доступе.")

        success, msg = await self.host_os.deploy_manager.commit_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    async def rollback_deploy_session(self) -> SkillResult:
        """
        Принудительно отменяет деплой-сессию и откатывает код фреймворка до исходного состояния.
        """

        if self.host_os.access_level < HostOSAccessLevel.OPERATOR:
            return SkillResult.fail("Отказано в доступе.")

        success, msg = self.host_os.deploy_manager.rollback_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

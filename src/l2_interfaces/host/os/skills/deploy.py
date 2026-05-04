"""
Навыки агента для безопасного переписывания системных файлов JAWL.
Доступны только начиная с уровня OPERATOR (2).
"""

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSDeploy:
    """Навыки для безопасного изменения исходного кода самого агента."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def start_deploy_session(self, reason: str) -> SkillResult:
        """
        Открывает деплой-сессию (режим самомодификации).
        Необходимо вызывать перед любыми попытками изменить исходный код в директории src/.
        Система начнет делать прозрачные бэкапы изменяемых файлов (Copy-on-Write).

        Args:
            reason: Обоснование изменения.
        """

        if not self.host_os.config.require_deploy_sessions:
            return SkillResult.ok(
                "Деплой-сессии отключены в конфигурации. Возможность изменения кода напрямую по умолчанию включена."
            )

        success, msg = self.host_os.deploy_manager.start_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def commit_deploy_session(self, test_path: str = "tests/src/test_builder.py tests/src/test_main.py", force: bool = False) -> SkillResult:
        """
        Завершает деплой-сессию. Физически проверяет код на синтаксические ошибки (SyntaxError) и запускает pytest.
        Если синтаксис сломан — коммит отменяется и сгорает 1 попытка. 
        При исчерпании попыток происходит автоматический Rollback файлов.

        Args:
            test_path: Путь к тестам для проверки. По умолчанию проверяет только Smoke-тесты (базовый запуск). 
            Если был изменен специфичный модуль - рекомендуется указать путь к его тестам для проверки работы (например, 'tests/src/l1/sql/').
            force: Принудительный коммит. Установить True, если тесты падают из-за причин, не связанных с измененным кодом (например, флакающие моки сети). Устанавливать True только в крайнем случае.
        """

        success, msg = await self.host_os.deploy_manager.commit_session(test_path=test_path, force=force)
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def rollback_deploy_session(self) -> SkillResult:
        """
        Принудительно отменяет деплой-сессию и откатывает код фреймворка до исходного состояния.
        """

        success, msg = self.host_os.deploy_manager.rollback_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

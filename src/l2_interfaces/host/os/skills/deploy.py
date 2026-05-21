"""
Agent skills for secure framework self-modification (JAWL source code updates).
Available only starting from Access Level >= OPERATOR (2).
"""

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access
from src.l3_agent.skills.registry import SkillResult, skill


class HostOSDeploy:
    """Skills for safe modification of the agent's own source code."""

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def start_deploy_session(self, reason: str) -> SkillResult:
        """
        Starts deploy session (self-modification mode).
        Required before modifying framework code.
        Initiates transparent file backups.
        """

        if not self.host_os.config.require_deploy_sessions:
            return SkillResult.ok(
                "Deploy sessions are disabled in the configuration. Direct code modification is enabled by default."
            )

        success, msg = self.host_os.deploy_manager.start_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def commit_deploy_session(
        self, test_path: str = "tests/unit/", force: bool = False
    ) -> SkillResult:
        """
        Commits deploy session.
        Runs syntax checker and pytest.
        Fails and consumes retry attempt on error.

        test_path: Path to tests.
        force: Ignores test failures (not recommended).
        """

        success, msg = await self.host_os.deploy_manager.commit_session(
            test_path=test_path, force=force
        )
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

    @skill()
    @require_access(HostOSAccessLevel.OPERATOR)
    async def rollback_deploy_session(self) -> SkillResult:
        """
        Forcefully aborts deploy session and rolls framework code back to initial state.
        """

        success, msg = self.host_os.deploy_manager.rollback_session()
        return SkillResult.ok(msg) if success else SkillResult.fail(msg)

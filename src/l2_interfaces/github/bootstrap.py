from typing import List, Any, TYPE_CHECKING

from src.utils.logger import system_logger

from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.skills.repositories import GithubRepositories
from src.l2_interfaces.github.skills.issues import GithubIssues
from src.l2_interfaces.github.skills.accounts import GithubAccounts
from src.l2_interfaces.github.skills.pull_requests import GithubPullRequests
from src.l2_interfaces.github.skills.local_git import GithubLocalGit

from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection

if TYPE_CHECKING:
    from src.main import System


def setup_github(system: "System", token: str | None) -> List[Any]:
    """Инициализирует интерфейс GitHub."""

    config = system.interfaces_config.github
    client = GithubClient(
        state=system.github_state,
        config=config,
        token=token,
    )

    # Регистрация навыков
    register_instance(GithubRepositories(client))
    register_instance(GithubIssues(client))
    register_instance(GithubAccounts(client))
    register_instance(GithubPullRequests(client))
    register_instance(GithubLocalGit(client))

    # Регистрация контекста
    system.context_registry.register_provider(
        name="github",
        provider_func=client.get_context_block,
        section=ContextSection.INTERFACES,
    )
    system_logger.info("[Github] Интерфейс загружен.")

    return [client]

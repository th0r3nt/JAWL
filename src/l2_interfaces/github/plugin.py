"""
GitHub interface plugin.
"""

from typing import List, Any, Dict, Optional
from src.utils.logger import main_logger
from src.l2_interfaces.base import BaseInterface
from src.l2_interfaces.github.state import GithubState
from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.events import GithubEvents
from src.l2_interfaces.github.skills.repositories import GithubRepositories
from src.l2_interfaces.github.skills.issues import GithubIssues
from src.l2_interfaces.github.skills.accounts import GithubAccounts
from src.l2_interfaces.github.skills.pull_requests import GithubPullRequests
from src.l2_interfaces.github.skills.local_git import GithubLocalGit
from src.l2_interfaces.github.skills.watchers import GithubWatchers
from src.l3_agent.skills.registry import register_instance
from src.l3_agent.context.registry import ContextSection
from src.system.container import SystemContainer
from src.utils.settings import InterfacesConfig


class GithubPlugin(BaseInterface):
    @property
    def name(self) -> str:
        return "GITHUB"

    @property
    def description(self) -> str:
        return "GitHub REST API and Git operations."

    def is_enabled(self, config: InterfacesConfig) -> bool:
        return config.github.enabled

    def setup(
        self, container: SystemContainer, env_vars: Dict[str, Optional[str]]
    ) -> List[Any]:
        config = container.interfaces_config.github
        state = GithubState(history_limit=config.history_limit)
        container.l0_states["github"] = state

        token = env_vars.get("GITHUB_TOKEN")
        client = GithubClient(state=state, config=config, token=token)
        events = GithubEvents(
            client=client,
            state=state,
            event_bus=container.event_bus,
            data_dir=container.local_data_dir,
            timezone=container.settings.system.timezone,
        )

        register_instance(GithubRepositories(client))
        register_instance(GithubIssues(client))
        register_instance(GithubAccounts(client))
        register_instance(GithubPullRequests(client))
        register_instance(GithubLocalGit(client))
        register_instance(GithubWatchers(client, events))

        container.context_registry.register_provider(
            "github", client.get_context_block, ContextSection.INTERFACES
        )
        main_logger.info("[Github] Interface loaded (Plugin).")
        return [client, events]

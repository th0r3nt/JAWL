"""
Guard decorators for verifying GitHub authorization rights.

Protect methods from being called without keys and dynamically hide them from the agent prompt,
saving context tokens and preventing hallucinations in Read-Only mode.
"""

from functools import wraps
from typing import Callable, Any
from src.l3_agent.skills.registry import SkillResult


def require_agent_account() -> Callable[..., Any]:
    """
    Blocks execution and hides the skill from the agent prompt
    if agent_account = False or token is missing.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "client", getattr(self, "github", None))
            if not client or not client.config.agent_account or not client.token:
                return SkillResult.fail(
                    "Error: This action requires 'agent_account: true' enabled in settings and a token added."
                )
            return await func(self, *args, **kwargs)

        # Lambda will return True if the skill SHOULD be visible in the prompt
        wrapper.__visibility_check__ = lambda instance: (
            (client := getattr(instance, "client", getattr(instance, "github", None)))
            is not None
            and client.config.agent_account
            and bool(client.token)
        )
        return wrapper

    return decorator


def require_github_token() -> Callable[..., Any]:
    """
    Requires only the presence of a token (not necessarily enabled agent_account).
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "client", getattr(self, "github", None))
            if not client or not client.token:
                return SkillResult.fail("Error: This action requires GITHUB_TOKEN.")

            return await func(self, *args, **kwargs)

        wrapper.__visibility_check__ = lambda instance: (
            (client := getattr(instance, "client", getattr(instance, "github", None)))
            is not None
            and bool(client.token)
        )
        return wrapper

    return decorator

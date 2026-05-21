"""
Guard decorators for verifying access rights.

Protect system calls at the method level, preventing execution
of dangerous functions if the agent has insufficient privileges.
"""

from functools import wraps
from typing import Callable, Any

from src.l3_agent.skills.registry import SkillResult
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def require_access(level: HostOSAccessLevel) -> Callable[..., Any]:
    """
    Guard decorator for verifying OS access level (Role-Based Access Control).

    Args:
        level: Minimum required access level to execute the function.
               E.g., HostOSAccessLevel.OPERATOR.

    Returns:
        Wrapper decorator. If privileges are insufficient, the function is not executed
        and SkillResult.fail is returned with a detailed explanation.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "host_os", None)
            if not client:
                return SkillResult.fail("[Guard] Internal error: HostOSClient not found.")

            if client.access_level < level:
                return SkillResult.fail(
                    f"Access denied. This action requires Access Level >= {level.value} ({level.name}). "
                    f"Current access level: {client.access_level.value} ({client.access_level.name})."
                )
            return await func(self, *args, **kwargs)

        # Save the required access level in the function attributes
        # This is used in get_skills_library() to dynamically hide unavailable skills from the prompt
        wrapper.__required_os_level__ = level.value
        return wrapper

    return decorator

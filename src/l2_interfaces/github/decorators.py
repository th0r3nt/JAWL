"""
Guard-декораторы для проверки прав авторизации в GitHub.
Защищают методы от вызова без ключей и динамически скрывают их из промпта агента,
экономя токены и предотвращая галлюцинации в режиме Read-Only.
"""

from functools import wraps
from typing import Callable, Any
from src.l3_agent.skills.registry import SkillResult


def require_agent_account() -> Callable[..., Any]:
    """
    Блокирует выполнение и скрывает навык из промпта агента,
    если agent_account = False или отсутствует токен.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "client", getattr(self, "github", None))
            if not client or not client.config.agent_account or not client.token:
                return SkillResult.fail(
                    "Ошибка: Для этого действия нужно включить 'agent_account: true' в настройках и добавить токен."
                )
            return await func(self, *args, **kwargs)

        # Лямбда вернет True, если навык ДОЛЖЕН быть виден в промпте
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
    Требует только наличия токена (не обязательно включенного agent_account).
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "client", getattr(self, "github", None))
            if not client or not client.token:
                return SkillResult.fail("Ошибка: Это действие требует наличия GITHUB_TOKEN.")
            
            return await func(self, *args, **kwargs)

        wrapper.__visibility_check__ = lambda instance: (
            (client := getattr(instance, "client", getattr(instance, "github", None)))
            is not None
            and bool(client.token)
        )
        return wrapper

    return decorator

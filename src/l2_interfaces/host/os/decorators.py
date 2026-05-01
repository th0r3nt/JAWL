"""
Guard-декораторы для проверки прав доступа.
Защищают системные вызовы на уровне методов, предотвращая выполнение
опасных функций, если у агента недостаточно прав.
"""

from functools import wraps
from typing import Callable, Any

from src.l3_agent.skills.registry import SkillResult
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def require_access(level: HostOSAccessLevel) -> Callable[..., Any]:
    """
    Guard-декоратор для проверки уровня доступа к ОС (Role-Based Access Control).

    Args:
        level: Минимальный требуемый уровень доступа для выполнения функции.
               Например, HostOSAccessLevel.OPERATOR.

    Returns:
        Обёртка-декоратор. Если прав не хватает, функция не выполняется
        и возвращается SkillResult.fail с подробным объяснением.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> SkillResult:
            client = getattr(self, "host_os", None)
            if not client:
                return SkillResult.fail("[Guard] Внутренняя ошибка: не найден HostOSClient.")

            if client.access_level < level:
                return SkillResult.fail(
                    f"Отказано в доступе. Для этого действия требуется Access Level >= {level.value} ({level.name}). "
                    f"Текущий уровень доступа: {client.access_level.value} ({client.access_level.name})."
                )
            return await func(self, *args, **kwargs)

        # Сохраняем требуемый уровень доступа в атрибутах функции
        # Это используется в get_skills_library() для динамического скрытия недоступных навыков из промпта
        wrapper.__required_os_level__ = level.value
        return wrapper

    return decorator

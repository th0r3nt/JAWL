from functools import wraps
from src.l3_agent.skills.registry import SkillResult
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def require_access(level: HostOSAccessLevel):
    """
    Guard-декоратор для проверки уровня доступа к ОС.
    Применяется к МЕТОДАМ классов, у которых есть атрибут self.host_os (HostOSClient).
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            client = getattr(self, "host_os", None)
            if not client:
                return SkillResult.fail(
                    "Внутренняя ошибка Guard: не найден HostOSClient для проверки прав."
                )

            if client.access_level < level:
                return SkillResult.fail(
                    f"Отказано в доступе. Для этого действия требуется Access Level >= {level.value} ({level.name}). "
                    f"Текущий уровень доступа: {client.access_level.value} ({client.access_level.name})."
                )
            return await func(self, *args, **kwargs)

        return wrapper

    return decorator

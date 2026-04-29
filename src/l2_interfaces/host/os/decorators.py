from functools import wraps
from src.l3_agent.skills.registry import SkillResult
from src.l2_interfaces.host.os.client import HostOSAccessLevel


def require_access(level: HostOSAccessLevel):
    """
    Guard-декоратор для проверки уровня доступа к ОС.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(self, *args, **kwargs):
            client = getattr(self, "host_os", None)
            if not client:
                return SkillResult.fail("[Guard] Внутренняя ошибка: не найден HostOSClient.")

            if client.access_level < level:
                return SkillResult.fail(
                    f"Отказано в доступе. Для этого действия требуется Access Level >= {level.value} ({level.name}). "
                    f"Текущий уровень доступа: {client.access_level.value} ({client.access_level.name})."
                )
            return await func(self, *args, **kwargs)

        # Сохраняем требуемый уровень доступа для динамической фильтрации в системном промпте
        wrapper.__required_os_level__ = level.value
        return wrapper

    return decorator

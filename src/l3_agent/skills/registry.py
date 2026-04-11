import inspect
import asyncio
from dataclasses import dataclass
from typing import Callable, Dict, Any

from src.utils.logger import system_logger


@dataclass
class SkillResult:
    is_success: bool
    message: str

    @classmethod
    def ok(cls, message: str) -> "SkillResult":
        return cls(is_success=True, message=message)

    @classmethod
    def fail(cls, message: str) -> "SkillResult":
        return cls(is_success=False, message=message)


_REGISTRY: Dict[str, Callable] = {}
_SKILL_DOCS: list[str] = []


def _build_skill_name(func: Callable, override: str = None, instance: Any = None) -> str:
    """Хелпер для формирования красивого имени функции."""
    if override:
        return override

    # Если это метод класса
    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

    # Если обычная функция
    segments = func.__module__.split(".")
    useless = {"src", "l0_state", "l1_databases", "l2_interfaces", "skills", "l3_agent"}
    clean_segments = [s for s in segments if s not in useless]
    return ".".join(clean_segments) + f".{func.__name__}"


def _register_callable(func: Callable, override: str = None, instance: Any = None):
    """Ядро регистрации. Формирует докстринги и сохраняет ссылку на вызов."""
    skill_name = _build_skill_name(func, override, instance)
    sig = inspect.signature(func)
    doc = inspect.getdoc(func) or "Без описания."

    _SKILL_DOCS.append(f"`{skill_name}{sig}` - {doc}")
    _REGISTRY[skill_name] = func
    system_logger.info(f"[System] Зарегистрирован скилл: {skill_name}")


def skill(name_override: str = None):
    """Декоратор. Умеет работать как с обычными функциями, так и с методами классов."""

    def decorator(func: Callable):
        sig = inspect.signature(func)

        # Если это метод класса, мы не можем регистрировать его сейчас (нет self)
        # Просто вешаем метку, чтобы зарегистрировать позже через инстанс
        if "self" in sig.parameters:
            func.__is_skill__ = True
            func.__skill_name_override__ = name_override
            return func

        # Если обычная функция - регистрируем сразу
        _register_callable(func, name_override)
        return func

    return decorator


def register_instance(instance: Any):
    """
    Проходится по объекту класса и регистрирует все методы, помеченные @skill.
    Вызывать в main.py после создания инстансов баз/интерфейсов.
    """
    for attr_name in dir(instance):
        method = getattr(instance, attr_name)
        if callable(method) and getattr(method, "__is_skill__", False):
            override = getattr(method, "__skill_name_override__", None)
            _register_callable(method, override, instance)


def get_skills_library() -> str:
    return "\n".join(_SKILL_DOCS)


async def execute_skill(thoughts: str, actions: list[dict]) -> str:
    system_logger.info(f"[Thoughts]: {thoughts}")
    
    if not actions:
        return "Цикл завершен: действий не передано."

    tasks = []
    for act in actions:
        name = act.get("tool_name")
        params = act.get("parameters", {})
        tasks.append(_run_single_skill(name, params))

    results = await asyncio.gather(*tasks)

    report = []
    for i, res in enumerate(results):
        status = "OK" if res.is_success else "ERROR"
        report.append(f"Action [{actions[i].get('tool_name')}]: {status} - {res.message}")

    return "\n".join(report)


async def _run_single_skill(name: str, params: dict) -> SkillResult:
    func = _REGISTRY.get(name)
    if not func:
        return SkillResult.fail(f"Скилл '{name}' не найден.")
    try:
        # Убираем возможный мусор, который LLM может попытаться скормить вместо параметров
        valid_params = {
            k: v for k, v in params.items() if k in inspect.signature(func).parameters
        }
        return await func(**valid_params)
    except Exception as e:
        return SkillResult.fail(f"Ошибка: {str(e)}")

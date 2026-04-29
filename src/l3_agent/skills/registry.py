import inspect
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, TypeVar

from pydantic import create_model, BaseModel, ValidationError

from src.utils.logger import system_logger
from src.utils._tools import truncate_text
from src.l3_agent.skills.schema import ActionCall


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


# Храним не просто функцию, а словарь: func и Pydantic-модель (Guard)
_REGISTRY: Dict[str, Dict[str, Any]] = {}
_SKILL_DOCS: list[str] = []
_CUSTOM_SKILL_DOCS: list[str] = []


def clear_registry():
    _REGISTRY.clear()
    _SKILL_DOCS.clear()
    _CUSTOM_SKILL_DOCS.clear()


def unregister_skill(skill_name: str):
    global _SKILL_DOCS, _CUSTOM_SKILL_DOCS
    if skill_name in _REGISTRY:
        del _REGISTRY[skill_name]

    _SKILL_DOCS = [doc for doc in _SKILL_DOCS if not doc.startswith(f"`{skill_name}(")]
    _CUSTOM_SKILL_DOCS = [
        doc for doc in _CUSTOM_SKILL_DOCS if not doc.startswith(f"`{skill_name}(")
    ]


def _build_skill_name(
    func: Callable, override: Optional[str] = None, instance: Optional[Any] = None
) -> str:
    if override:
        return override

    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

    segments = func.__module__.split(".")
    useless = {"src", "l0_state", "l1_databases", "l2_interfaces", "skills", "l3_agent"}
    clean_segments = [s for s in segments if s not in useless]
    return ".".join(clean_segments) + f".{func.__name__}"


def _create_pydantic_guard(func: Callable, skill_name: str) -> type[BaseModel]:
    """Динамически генерирует Pydantic схему на основе сигнатуры функции."""
    sig = inspect.signature(func)
    fields = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue

        annotation = (
            param.annotation if param.annotation is not inspect.Parameter.empty else Any
        )
        default = param.default if param.default is not inspect.Parameter.empty else ...

        fields[name] = (annotation, default)

    safe_name = skill_name.replace(".", "_") + "_Guard"
    return create_model(safe_name, **fields)


def _register_callable(
    func: Callable, override: Optional[str] = None, instance: Optional[Any] = None
):
    skill_name = _build_skill_name(func, override, instance)
    sig = inspect.signature(func)

    formatted_params = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        param_str = str(param)
        if param.default is inspect.Parameter.empty and param.kind not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            param_str += " <REQUIRED>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    raw_doc = inspect.getdoc(func) or "Без описания."
    clean_doc = " ".join(raw_doc.split())

    _SKILL_DOCS.append(f"`{skill_name}{clean_sig}` - {clean_doc}")

    # Генерируем Guard
    guard_model = _create_pydantic_guard(func, skill_name)
    _REGISTRY[skill_name] = {"func": func, "guard": guard_model}

    system_logger.info(f"[Skills] Зарегистрирован скилл: {skill_name}")


def register_custom_callable(func: Callable, skill_name: str, description: str, filepath: str):
    sig = inspect.signature(func)

    formatted_params = []
    for name, param in sig.parameters.items():
        param_str = f"{name}: {param.annotation.__name__ if hasattr(param.annotation, '__name__') else param.annotation}"
        if param.default is inspect.Parameter.empty:
            param_str += " <REQUIRED>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    clean_doc = " ".join(description.split())

    doc_str = f"`{skill_name}{clean_sig}` - {clean_doc} [Файл: {filepath}]"
    _CUSTOM_SKILL_DOCS.append(doc_str)

    guard_model = _create_pydantic_guard(func, skill_name)
    _REGISTRY[skill_name] = {"func": func, "guard": guard_model}

    system_logger.info(f"[Skills] Зарегистрирован кастомный скилл: {skill_name}")


F = TypeVar("F", bound=Callable[..., Any])


def skill(name_override: Optional[str] = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        if "self" in sig.parameters:
            setattr(func, "__is_skill__", True)
            setattr(func, "__skill_name_override__", name_override)
            return func

        _register_callable(func, name_override)
        return func

    return decorator


def register_instance(instance: Any):
    for attr_name in dir(instance):
        method = getattr(instance, attr_name)
        if callable(method) and getattr(method, "__is_skill__", False):
            override = getattr(method, "__skill_name_override__", None)
            _register_callable(method, override, instance)


def get_skills_library() -> str:
    base = "\n".join(_SKILL_DOCS)
    if _CUSTOM_SKILL_DOCS:
        base += "\n\n### CUSTOM SKILLS\n" + "\n".join(_CUSTOM_SKILL_DOCS)
    return base


async def execute_skill(actions: list[ActionCall]) -> str:
    if not actions:
        return "Цикл завершен: действий не передано."

    tasks = []
    for act in actions:
        name = act.tool_name
        params = act.parameters

        params_str = truncate_text(
            str(params), max_chars=250, suffix="... [Параметры обрезаны]"
        )

        system_logger.info(f"[Agent Action] {name}({params_str})")
        tasks.append(call_skill(name, params))

    results = await asyncio.gather(*tasks)

    report = []
    for i, res in enumerate(results):
        report.append(f"\n* Action [{actions[i].tool_name}]: {res.message}")

    return "\n".join(report)


async def call_skill(name: str, params: dict) -> SkillResult:
    item = _REGISTRY.get(name)
    if not item:
        err_msg = f"Скилл '{name}' не найден."
        system_logger.info(f"[Agent Action Result] {err_msg}")
        return SkillResult.fail(err_msg)

    func = item["func"]
    guard_model = item["guard"]

    # Pydantic Guard Layer: валидация и авто-каст типов
    try:
        validated_params = guard_model(**params)
        clean_kwargs = validated_params.model_dump()

    except ValidationError as e:
        errors = []

        for err in e.errors():
            loc = ".".join(map(str, err["loc"]))
            errors.append(f"- Аргумент '{loc}': {err['msg']}")

        err_msg = (
            "Ошибка валидации параметров:\n"
            + "\n".join(errors)
            + "\nРекомендуется исправить типы данных и вызвать функцию снова."
        )

        system_logger.warning(f"[Guard] Отклонен вызов {name}: Ошибка типов.")
        return SkillResult.fail(err_msg)

    # Выполнение бизнес-логики
    try:
        result = await func(**clean_kwargs)

        res_msg = truncate_text(
            str(result.message), max_chars=500, suffix="... [Результат обрезан для логов]"
        )
        status = "Success" if result.is_success else "Fail"
        system_logger.info(f"[Agent Action Result] {name} ({status}): {res_msg}")

        return result
    
    except Exception as e:
        system_logger.info(f"[Agent Action Result] Ошибка в скилле {name}: {str(e)}")
        return SkillResult.fail(f"Внутренняя ошибка навыка: {str(e)}")

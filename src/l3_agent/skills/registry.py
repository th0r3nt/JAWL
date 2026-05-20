"""
Глобальный реестр навыков (Skills Registry) и слой защиты (Guard Layer).

Отвечает за регистрацию нативных и кастомных функций, динамическое создание
Pydantic-моделей для валидации аргументов (защита от галлюцинаций LLM) и
Role-Based Access Control (RBAC) для субагентов.
"""

import inspect
import asyncio
from dataclasses import dataclass
from typing import Optional, Callable, Dict, Any, TypeVar, List
import logging

from pydantic import create_model, BaseModel, ValidationError

from src.utils.logger import agent_logger
from src.utils._tools import truncate_text
from src.utils.settings import SubconsciousConfig

from src.l3_agent.skills.schema import ActionCall
from src.l3_agent.swarm.roles import SubagentRole
from src.l3_agent.subconscious.schema import Pattern


@dataclass
class SkillResult:
    """
    Стандартизированный ответ любого инструмента агента.
    """

    is_success: bool
    message: str

    @classmethod
    def ok(cls, message: str) -> "SkillResult":
        return cls(is_success=True, message=message)

    @classmethod
    def fail(cls, message: str) -> "SkillResult":
        return cls(is_success=False, message=message)


_REGISTRY: Dict[str, Dict[str, Any]] = {}


def clear_registry() -> None:
    """Очищает глобальный реестр (вызывается при ребуте агента)."""
    _REGISTRY.clear()


def unregister_skill(skill_name: str) -> None:
    """Удаляет навык из реестра по имени."""
    if skill_name in _REGISTRY:
        del _REGISTRY[skill_name]


def _build_skill_name(
    func: Callable[..., Any], override: Optional[str] = None, instance: Optional[Any] = None
) -> str:
    """
    Генерирует чистое имя функции (убирая системные префиксы src.l2_interfaces...).
    """

    if override:
        return override

    if instance:
        return f"{instance.__class__.__name__}.{func.__name__}"

    segments = func.__module__.split(".")
    useless = {"src", "l0_state", "l1_databases", "l2_interfaces", "skills", "l3_agent"}
    clean_segments = [s for s in segments if s not in useless]

    return ".".join(clean_segments) + f".{func.__name__}"


def _create_pydantic_guard(func: Callable[..., Any], skill_name: str) -> type[BaseModel]:
    """
    Динамически генерирует Pydantic модель (Guard) на основе сигнатуры функции (type-hints).
    Обеспечивает Type Coercion (приведение типов) и защиту от мусорных параметров.
    """

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
    func: Callable[..., Any],
    override: Optional[str] = None,
    instance: Optional[Any] = None,
    swarm: Optional[List[SubagentRole]] = None,
    subconscious: Optional[List[Pattern]] = None,
    hidden: bool = False,
) -> None:
    """
    Внутренний метод регистрации Python-функции в реестре.
    """

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
            param_str += " <REQ>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    raw_doc = inspect.getdoc(func) or "Без описания."
    clean_doc = " ".join(raw_doc.split())

    doc_str = f"{skill_name}{clean_sig} - {clean_doc}"

    _REGISTRY[skill_name] = {
        "func": func,
        "guard": _create_pydantic_guard(func, skill_name),
        "instance": instance,
        "doc_string": doc_str,
        "is_custom": False,
        "swarm": swarm or [],
        "subconscious": subconscious or [],
        "hidden": hidden,
    }
    log = f"[Skills] Зарегистрирован скилл: {skill_name}"
    agent_logger.debug(log)


def register_custom_callable(
    func: Callable[..., Any], skill_name: str, description: str, filepath: str
) -> None:
    """
    Регистрирует кастомный прокси-скилл (скрипт из песочницы).
    """

    sig = inspect.signature(func)
    formatted_params = []
    for name, param in sig.parameters.items():
        param_str = f"{name}: {param.annotation.__name__ if hasattr(param.annotation, '__name__') else param.annotation}"
        if param.default is inspect.Parameter.empty:
            param_str += " <REQ>"
        formatted_params.append(param_str)

    clean_sig = f"({', '.join(formatted_params)})"
    clean_doc = " ".join(description.split())
    doc_str = f"`{skill_name}{clean_sig}` - {clean_doc} [Файл: {filepath}]"

    _REGISTRY[skill_name] = {
        "func": func,
        "guard": _create_pydantic_guard(func, skill_name),
        "instance": None,
        "doc_string": doc_str,
        "is_custom": True,
        "swarm": [],
        "subconscious": [],
        "hidden": False,
    }
    log = f"[Skills] Зарегистрирован кастомный скилл: {skill_name}"
    agent_logger.info(log)


F = TypeVar("F", bound=Callable[..., Any])


def skill(
    name_override: Optional[str] = None,
    swarm: Optional[List[SubagentRole]] = None,
    subconscious: Optional[List[Pattern]] = None,
    hidden: bool = False,
) -> Callable[[F], F]:
    """
    Декоратор, который автоматически регистрирует новый навык для агента.
    Берет dockstring, аргументы и их типы, формируя контекстный блок 'function(arg1: type) - dockstring'.

    Args:
        name_override: Переопределение названия функции (по умолчанию берется 'Класс.имя_функции').
        swarm: Массив субагентов, которые могут использовать этот навык (RBAC).
        subconscious: Массив паттернов подсознания, которые могут использовать этот навык.
        hidden: Если True - главный агент не будет видеть этот навык (полезно для системных функций).
    """

    def decorator(func: F) -> F:
        sig = inspect.signature(func)
        if "self" in sig.parameters:
            setattr(func, "__is_skill__", True)
            setattr(func, "__skill_name_override__", name_override)
            setattr(func, "__swarm__", swarm)
            setattr(func, "__subconscious__", subconscious)
            setattr(func, "__skill_hidden__", hidden)
            return func
        _register_callable(
            func, name_override, swarm=swarm, subconscious=subconscious, hidden=hidden
        )
        return func

    return decorator


def register_instance(instance: Any) -> None:
    """Регистрирует все задекорированные методы внутри переданного инстанса класса."""
    for attr_name in dir(instance):
        method = getattr(instance, attr_name)
        if callable(method) and getattr(method, "__is_skill__", False):
            override = getattr(method, "__skill_name_override__", None)
            swarm = getattr(method, "__swarm__", None)
            subconscious = getattr(method, "__subconscious__", None)
            hidden = getattr(method, "__skill_hidden__", False)
            _register_callable(
                method,
                override,
                instance,
                swarm=swarm,
                subconscious=subconscious,
                hidden=hidden,
            )


def get_skills_library(subconscious_config: Optional[SubconsciousConfig] = None) -> str:
    """
    Собирает все навыки. Автоматически скрывает навыки, если они делегированы
    активному подсознательному паттерну, чтобы разгрузить контекст Оркестратора.
    """
    active_docs = []
    custom_docs = []

    for skill_name in sorted(_REGISTRY.keys()):
        data = _REGISTRY[skill_name]

        if data.get("hidden", False):
            continue

        if data.get("is_custom"):
            custom_docs.append(data["doc_string"])
            continue

        # Dynamic Visibility для Подсознания
        if subconscious_config and subconscious_config.enabled:
            patterns_list = data.get("subconscious", [])
            if patterns_list:
                # Проверяем, включен ли хотя бы один паттерн, требующий этот навык
                is_used_by_active_pattern = False
                for p in patterns_list:
                    p_cfg = getattr(subconscious_config.patterns, p.value, None)
                    if p_cfg and p_cfg.enabled:
                        is_used_by_active_pattern = True
                        break

                # Если навык обслуживает включенное подсознание - скрываем его от главного агента, чтобы не перегружать контекст
                if is_used_by_active_pattern:
                    continue

        func = data["func"]
        instance = data["instance"]
        doc = data["doc_string"]

        req_level = getattr(func, "__required_os_level__", None)
        if req_level is not None and instance is not None:
            host_os = getattr(instance, "host_os", None)
            if host_os is not None and host_os.access_level.value < req_level:
                continue

        visibility_check = getattr(func, "__visibility_check__", None)
        if visibility_check and instance is not None:
            try:
                if not visibility_check(instance):
                    continue
            except Exception as e:
                # Ошибка в кастомном декораторе видимости
                agent_logger.warning(
                    f"[Skills Registry] Исключение в __visibility_check__ для {skill_name}: {e}"
                )

        active_docs.append(doc)

    formatted_docs = []
    last_prefix = ""
    for doc in active_docs:
        skill_name_match = doc.split("(", 1)[0].replace("`", "")
        prefix = skill_name_match.split(".")[0] if "." in skill_name_match else ""

        if last_prefix and prefix != last_prefix:
            formatted_docs.append("")

        formatted_docs.append(doc)
        last_prefix = prefix

    base = "\n".join(formatted_docs)
    if custom_docs:
        base += "\n\n### CUSTOM SKILLS\n" + "\n".join(custom_docs)
    return base


async def execute_skill(
    actions: List[ActionCall], logger: logging.Logger = agent_logger
) -> str:
    """
    Асинхронно и параллельно выполняет массив запрошенных агентом действий.

    Args:
        actions: Список объектов ActionCall.
        logger: Логгер целевой подсистемы (по умолчанию agent_logger).
    """
    if not actions:
        return "Цикл завершен: действий не передано."

    tasks = []
    for act in actions:
        name = act.tool_name
        params = act.parameters
        # Убрали ручное логирование [Agent Action] отсюда, оно теперь внутри call_skill
        tasks.append(call_skill(name, params, logger=logger))

    results = await asyncio.gather(*tasks)
    report = [f"* {actions[i].tool_name}: {res.message}" for i, res in enumerate(results)]
    return "\n".join(report)


async def call_skill(
    name: str, params: Dict[str, Any], logger: logging.Logger = agent_logger
) -> SkillResult:
    """
    Низкоуровневый вызов отдельного навыка с прогоном параметров через Pydantic Guard Layer.
    """
    params_str = truncate_text(str(params), max_chars=250, suffix="... [Параметры обрезаны]")

    logger.info(f"[Agent Action] {name}({params_str})")

    item = _REGISTRY.get(name)
    if not item:
        err_msg = f"Скилл '{name}' не найден."
        logger.warning(f"[Agent Action Result] {err_msg}")
        return SkillResult.fail(err_msg)

    func = item["func"]
    guard_model = item["guard"]

    try:
        validated_params = guard_model(**params)
        clean_kwargs = validated_params.model_dump()
    except ValidationError as e:
        errors = [
            f"- Аргумент '{err['loc'][0] if err['loc'] else 'unknown'}': {err['msg']}"
            for err in e.errors()
        ]
        err_msg = "Ошибка валидации параметров:\n" + "\n".join(errors)
        logger.warning(f"[Guard] Отклонен вызов {name}: Ошибка типов.")
        return SkillResult.fail(err_msg)

    try:
        result = await func(**clean_kwargs)
        res_msg = truncate_text(
            str(result.message), max_chars=200, suffix="... [Результат обрезан для логов]"
        )
        status = "Success" if result.is_success else "Fail"

        logger.info(f"[Agent Action Result] {name} ({status}): {res_msg}")
        return result
    except Exception as e:
        logger.error(f"[Agent Action Result] Ошибка в скилле {name}: {str(e)}")
        return SkillResult.fail(f"Внутренняя ошибка навыка: {str(e)}")

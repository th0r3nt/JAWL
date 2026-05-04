import pytest
from pydantic import ValidationError
from src.l3_agent.skills.registry import _create_pydantic_guard


def dummy_target_function(req_str: str, opt_int: int = 10, opt_bool: bool = False):
    """Целевая функция с тайп-хинтами."""
    pass


def test_pydantic_guard_generation_and_validation():
    """Тест: Guard Layer корректно собирает Pydantic модель из сигнатуры функции."""

    GuardModel = _create_pydantic_guard(dummy_target_function, "test.dummy")

    # 1. Валидный payload
    obj1 = GuardModel(req_str="hello")
    assert obj1.req_str == "hello"
    assert obj1.opt_int == 10  # default
    assert obj1.opt_bool is False

    # 2. Type Coercion (Приведение типов: LLM ошиблась и прислала строку вместо числа)
    # req_str теперь строка, так как Pydantic v2 строг к int -> str. Нас интересуют именно конверсии str -> int
    obj2 = GuardModel(req_str="123", opt_int="42", opt_bool="true")
    assert obj2.req_str == "123"
    assert obj2.opt_int == 42  # str -> int
    assert obj2.opt_bool is True  # str -> bool

    # 3. Отсутствие обязательного аргумента
    with pytest.raises(ValidationError) as exc:
        GuardModel(opt_int=5)

    assert "req_str" in str(exc.value)
    assert "Field required" in str(exc.value)

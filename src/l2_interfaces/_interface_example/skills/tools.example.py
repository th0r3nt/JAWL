"""
Навыки (Skills) для агента.

Это "руки" агента. Классы здесь содержат функции, задекорированные `@skill()`.
Pydantic Guard Layer динамически читает type-hints ваших функций, конвертирует их
в JSON Schema и отдает LLM модели.

Небольшой совет:
Не плодите God Objects.

Если этот файл разрастается (больше 200-300 строк или объединяет разный функционал),
Обязательно дробите его на логические подфайлы в директории `skills/`.
Например:

- `skills/messages.py` (отправка/чтение сообщений)
- `skills/moderation.py` (бан/мут)
- `skills/files.py` -> `skills/files/reader.py`, `skills/files/writer.py`

Смотрите пример в `src/l2_interfaces/host/os/skills/files/`.

Если в этом фреймворке появятся файлы по 1000 строк - оригинальный разработчик подаст на вас жалобу в Гаагский трибунал (шутка).
"""

from typing import Optional, Any

# Импорты для регистрации навыков:
from src.l3_agent.skills.registry import skill, SkillResult

# Если необходимо ограничить доступ субагентам (RBAC):
# from src.l3_agent.swarm.roles import Subagents


class ExampleSkills:
    """Инструменты агента для работы с пользовательским API."""

    def __init__(self, client: Any) -> None:
        """Инжектим клиент, через который мы будем делать реальные запросы к API."""
        self.client = client

    # Аргумент swarm_roles=[...] разрешает вызывать этот навык только определенным субагентам.
    # Если swarm_roles не передан, субагенты не увидят этот навык вообще. Главный оркестратор видит всё всегда (если не поставить hidden=True).

    # @skill(swarm_roles=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    @skill()
    async def my_custom_tool(self, text_param: str, count: Optional[int] = 1) -> SkillResult:
        """
        Идеальный, подробный докстринг. Именно этот текст LLM увидит в своем System Prompt.
        Объясняйте здесь, для чего нужна функция и что делают её аргументы.

        Args:
            text_param: Текст, который нужно обработать.
            count: Количество итераций (по умолчанию 1).
        """

        # Pydantic Guard Layer автоматически проверит, чтобы `count` был `int` (даже если LLM пришлет "5" как строку),
        # а если LLM пришлет сюда массив, функция даже не запустится - Guard Layer сам вернет ошибку агенту.

        try:
            # 1. Вызываем клиент для взаимодействия с внешним миром
            # response = await self.client.do_something(text_param, count)

            # 2. Логируем успешное действие в истории стейта (если нужно)
            # self.client.state.add_history(f"Вызван my_custom_tool с параметром {text_param}")

            # 3. Обязательно возвращаем SkillResult.ok() в случае успеха
            return SkillResult.ok(
                f"Инструмент успешно отработал. Текст: {text_param}, раз: {count}"
            )

        except Exception as e:
            # Возвращаем SkillResult.fail() с подробной ошибкой, чтобы агент мог проанализировать
            # проблему в `thoughts` на следующем шаге ReAct-цикла.
            return SkillResult.fail(f"Ошибка при вызове внешнего API: {e}")

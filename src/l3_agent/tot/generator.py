"""
Генератор дерева мыслей (ToT Generator).
Оркестрирует сборку отфильтрованного контекста, вызов LLM и форматирование результата.
"""

import asyncio
import time
import openai
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.logger import system_logger
from src.utils.token_tracker import TokenTracker

from src.l0_state.agent.state import AgentState
from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.tot.schema import TOT_SCHEMA, TreeResponse


class ToTGenerator:
    """Генератор стратегических веток."""

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str,
        branches_count: int,
        prompt_builder: PromptBuilder,
        context_registry: ContextRegistry,
        agent_state: AgentState,
        token_tracker: TokenTracker,
        root_dir: Path,
        timezone: int,
    ) -> None:
        self.llm = llm_client
        self.model_name = model_name
        self.branches_count = branches_count
        self.context_registry = context_registry
        self.agent_state = agent_state
        self.tracker = token_tracker
        self.timezone = timezone

        # ЛИЧНОСТЬ АГЕНТА
        personality_prompt = prompt_builder._gather_markdown("personality")

        # СИСТЕМНЫЕ ИНСТРУКЦИИ
        prompt_path = root_dir / "src" / "l3_agent" / "tot" / "prompt" / "INSTRUCTIONS.md"
        tot_instructions = (
            prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
        )

        # ОБЩИЙ ПРОМПТ
        self.system_prompt = f"{personality_prompt}\n\n\n{tot_instructions}".strip()

    # Главная функция генерации дерева мыслей
    async def generate(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Генерирует Markdown блок с деревом мыслей на основе текущей ситуации.
        """

        system_logger.info(
            f"[Tree of Thoughts] Запуск генерации дерева мыслей (Модель: {self.model_name})."
        )

        # =================================================
        # КОНТЕКСТ

        context = await self._build_filtered_context(event_name, payload, missed_events)
        context += f"\n\n# CURRENT TASK \nСгенерировать {self.branches_count} различных стратегий-веток для текущей ситуации."

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context},
        ]

        self.tracker.add_input_record(messages, log_prefix="[Tree of Thoughts LLM]")
        await asyncio.to_thread(self._dump_context_to_file, messages)

        # =================================================
        # ВЫЗОВ LLM

        raw_json = await self._call_llm(messages)
        if not raw_json:
            return None

        # =================================================
        # ПАРСИНГ И ФОРМАТИРОВАНИЕ

        try:
            parsed = TreeResponse.model_validate_json(raw_json)
            return self._format_markdown(parsed)
        except Exception as e:
            system_logger.error(f"[Tree of Thoughts] Ошибка парсинга дерева мыслей: {e}")
            return None

    # ====================================================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ====================================================================================

    async def _build_filtered_context(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> str:
        """
        Собирает контекст, исключая тяжелые скиллы и лишние данные.
        """

        allowed_sections = {
            ContextSection.AGENT_STATE,
            ContextSection.DRIVES,
            ContextSection.TRAITS,
            ContextSection.MENTAL_STATES,
            ContextSection.TASKS,
            ContextSection.RAG_MEMORIES,
            ContextSection.RECENT_TICKS,
            ContextSection.HEARTBEAT,
        }

        # Получаем все данные из реестра
        all_blocks = await self.context_registry.gather_all(
            event_name=event_name,
            payload=payload,
            missed_events=missed_events,
            agent_state=self.agent_state,
        )

        # Фильтруем
        filtered_blocks = []
        # Идем по отсортированным (внутри реестра) ключам
        sorted_names = sorted(
            self.context_registry._providers.keys(),
            key=lambda k: self.context_registry._providers[k]["section"].value,
        )

        for name in sorted_names:
            section = self.context_registry._providers[name]["section"]
            if section in allowed_sections and name in all_blocks:
                filtered_blocks.append(all_blocks[name])

        return "\n\n\n".join(filtered_blocks).strip()

    def _format_markdown(self, tree: TreeResponse) -> str:
        """
        Превращает Pydantic-объект в красивый Markdown блок.
        """
        if not tree.branches:
            return ""
    
        step = self.agent_state.current_step

        lines = ["## TREE OF THOUGHTS\n"]
        lines.append(f"*Время генерации: Шаг {step}*\n")

        for i, branch in enumerate(tree.branches, 1):
            lines.append(f"**Ветка: {branch.name}**")
            lines.append(f"*Описание:* {branch.description}")

            if branch.estimated_speed:
                lines.append(f"*Скорость:* {branch.estimated_speed}")

            if branch.complexity:
                lines.append(f"*Сложность:* {branch.complexity}")

            if branch.risk_assessment:
                lines.append(f"*Риски:* {branch.risk_assessment}")

            lines.append("")  # Пустая строка между ветками

        return "\n".join(lines).strip()

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """
        Обрабатывает запросы к LLM, ротацию ключей и кулдауны.
        """

        for _ in range(3):
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=TOT_SCHEMA,
                    tool_choice={"type": "function", "function": {"name": "submit_tree"}},
                )

                msg_obj = response.choices[0].message
                if msg_obj.tool_calls:
                    raw_answer = str(msg_obj.tool_calls[0].function.arguments)
                    self.tracker.add_output_record(
                        raw_answer, log_prefix="[Tree of Thoughts LLM]"
                    )
                    return raw_answer
                return None

            except RuntimeError as e:
                if "исчерпали лимиты" in str(e):
                    import re

                    match = re.search(r"подождать (\d+) сек", str(e))
                    wait_sec = int(match.group(1)) if match else 10
                    system_logger.warning(
                        f"[Tree of Thoughts] Все ключи в кулдауне. Ждем {wait_sec}с."
                    )
                    await asyncio.sleep(wait_sec + 1)
                    continue
                return None

            except openai.RateLimitError as e:
                # Базовая обработка лимитов
                wait_time = 30
                if e.response is not None:
                    headers = e.response.headers
                    retry_after = headers.get("retry-after") or headers.get(
                        "x-ratelimit-reset"
                    )
                    if retry_after:
                        try:
                            if headers.get("retry-after-ms"):
                                wait_time = max(1, int(int(retry_after) / 1000))
                            else:
                                wait_time = int(float(retry_after))

                            if wait_time > time.time():
                                wait_time = int(wait_time - time.time())
                        except ValueError:
                            pass
                wait_time = max(2, min(wait_time, 120))
                system_logger.warning(
                    f"[Tree of Thoughts] Rate Limit (429). Кулдаун ключа на {wait_time}с."
                )
                self.llm.rotator.cooldown_key(session.api_key, wait_time)

                if self.llm.rotator.total_keys() == 1:
                    await asyncio.sleep(wait_time + 1)
                else:
                    await asyncio.sleep(1)

                continue
            except Exception as e:
                system_logger.error(f"[Tree of Thoughts] LLM ошибка: {e}")
                await asyncio.sleep(2)
                continue

        return None

    def _dump_context_to_file(self, messages: List[Dict[str, Any]]) -> None:
        """Сохраняет промпт подсознания для отладки."""
        try:
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(log_dir / "last_tot_prompt.md", "w", encoding="utf-8") as f:
                f.write("# TREE OF THOUGHTS DUMP\n\n---\n\n")
                for m in messages:
                    role = getattr(
                        m,
                        "role",
                        m.get("role", "unknown") if isinstance(m, dict) else "unknown",
                    )
                    content = getattr(
                        m, "content", m.get("content", "") if isinstance(m, dict) else ""
                    )
                    f.write(f"### Role: {role}\n{content}\n\n---\n")
        except Exception as e:
            system_logger.error(f"[Tree of Thoughts] Не удалось сохранить промпт: {e}")

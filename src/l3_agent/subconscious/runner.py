import asyncio
import openai
import time
import re
from pathlib import Path
from typing import List, Tuple, Optional

from src.utils.logger import main_logger, subc_logger
from src.utils.token_tracker import TokenTracker

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.skills.schema import AgentResponse, ActionCall, ACTION_SCHEMA, parse_llm_json
from src.l3_agent.skills.registry import _REGISTRY, call_skill
from src.l3_agent.subconscious.schema import Pattern

# Импортируем менеджеры
from src.l1_databases.sql.manager import SQLManager
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.graph.manager import GraphManager
from src.l1_databases.graph.schema import GRAPH_NODE_TABLE


class SubconsciousRunner:
    """Облегченный цикл ReAct для фоновой работы с базами данных."""

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str,
        sql_manager: SQLManager,
        vector_manager: VectorManager,
        graph_manager: GraphManager,
        token_tracker: TokenTracker,
        root_dir: Path,
        max_steps: int = 4,
    ) -> None:
        self.llm = llm_client
        self.model_name = model_name
        self.sql = sql_manager
        self.vector = vector_manager
        self.graph = graph_manager
        self.tracker = token_tracker
        self.root_dir = root_dir
        self.max_steps = max_steps

    # ========================================================
    # ОСНОВНОЙ ЦИКЛ RUN
    # ========================================================

    async def run(self, pattern: Pattern, ticks_to_analyze: int) -> None:
        """Запускает мини-цикл раздумий подсознания."""
        log = f"[Subconscious] Запуск паттерна {pattern.value.upper()} (LLM: {self.model_name})."
        subc_logger.info(log)

        prompt = self._get_prompt(pattern)
        allowed_skills_doc = self._get_allowed_skills(pattern)

        # Динамически собираем контекст
        context = await self._build_dynamic_context(pattern, ticks_to_analyze)

        full_user_msg = f"{context}\n\n## AVAILABLE SKILLS\nВам разрешено использовать исключительно следующие инструменты:\n{allowed_skills_doc}"

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": full_user_msg},
        ]
        self.tracker.add_input_record(
            messages, log_prefix="[Subconscious]", logger=subc_logger
        )

        # Мини-ReAct Loop
        for step in range(self.max_steps):
            await asyncio.to_thread(self._dump_context_to_file, messages, pattern)
            raw_answer = await self._call_llm(messages)
            if not raw_answer:
                break

            parsed, error = self._parse_response(raw_answer)
            if error:
                messages.append({"role": "assistant", "content": raw_answer})
                messages.append({"role": "user", "content": f"System Error: {error}"})
                continue

            if not parsed.actions:
                log = f"[Subconscious] Паттерн {pattern.value.upper()} штатно завершил работу."
                subc_logger.info(log)
                break

            results = await self._execute_actions(parsed.actions, pattern)
            messages.append({"role": "assistant", "content": raw_answer})
            messages.append({"role": "user", "content": results})

        log = f"[Subconscious] Цикл паттерна {pattern.value.upper()} окончен."
        subc_logger.debug(log)

    # ========================================================
    # СТРАТЕГИИ СБОРКИ КОНТЕКСТА ДЛЯ РАЗНЫХ ПАТТЕРНОВ
    # ========================================================

    async def _build_ticks_context(self, limit: int) -> str:
        """Собирает недавние тики. (Используется Консолидацией)."""
        return await self.sql.ticks.get_full_context_block(limit=limit)

    async def _build_reflection_context(self, limit: int) -> str:
        """Собирает тики + текущее состояние CRM и Черт характера."""
        ticks_ctx = await self._build_ticks_context(limit)

        # Получаем сырые данные напрямую через методы скиллов, которые возвращают SkillResult
        ms_res = await self.sql.mental_states.get_mental_states()
        tr_res = await self.sql.personality_traits.get_traits()

        return f"{ticks_ctx}\n\n{ms_res.message}\n\n{tr_res.message}"

    async def _build_forgetting_context(self, limit: int) -> str:
        """Собирает дампы баз данных для чистки мусора."""
        k_res = await self.vector.knowledge.get_all_knowledge(limit=limit)
        t_res = await self.vector.thoughts.get_all_thoughts(limit=limit)

        # Для графа у нас нет прямого скилла "получить всё", поэтому делаем безопасный запрос
        def _get_graph_nodes():
            try:
                res = self.graph.db.conn.execute(
                    f"MATCH (n:{GRAPH_NODE_TABLE}) RETURN n.name, n.category, n.description LIMIT {limit}"
                )
                nodes = []
                while res.has_next():
                    row = res.get_next()
                    nodes.append(f"- [{row[1]}] {row[0]}: {row[2]}")
                return "\n".join(nodes) if nodes else "Граф пуст."
            except Exception:
                return "Граф пуст или недоступен."

        graph_str = await asyncio.to_thread(_get_graph_nodes)

        return (
            f"## VECTOR KNOWLEDGE (Recent {limit})\n{k_res.message}\n\n"
            f"## VECTOR THOUGHTS (Recent {limit})\n{t_res.message}\n\n"
            f"## GRAPH CONCEPTS (Recent {limit})\n{graph_str}"
        )

    async def _build_dynamic_context(self, pattern: Pattern, limit: int) -> str:
        """Маршрутизатор контекста."""
        if pattern == Pattern.CONSOLIDATION:
            return await self._build_ticks_context(limit)

        elif pattern == Pattern.REFLECTION:
            return await self._build_reflection_context(limit)
        elif pattern == Pattern.FORGETTING:
            return await self._build_forgetting_context(limit)

        return "Нет данных."

    # ========================================================
    # Служебные методы
    # ========================================================

    async def _call_llm(self, messages: list) -> Optional[str]:
        for attempt in range(5):
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=ACTION_SCHEMA,
                    temperature=0.3,
                )
                msg_obj = response.choices[0].message
                ans = (
                    str(msg_obj.tool_calls[0].function.arguments)
                    if msg_obj.tool_calls
                    else msg_obj.content or ""
                )
                self.tracker.add_output_record(
                    ans, log_prefix="[Subconscious]", logger=subc_logger
                )
                return ans

            except RuntimeError as e:
                # Все ключи в бане
                if "исчерпали лимиты" in str(e):
                    match = re.search(r"подождать (\d+) сек", str(e))
                    wait_sec = int(match.group(1)) if match else 10

                    log = f"[Subconscious] Все ключи в кулдауне. Ждем {wait_sec}с."
                    subc_logger.warning(log)

                    await asyncio.sleep(wait_sec + 1)
                    continue

                return None

            except openai.RateLimitError as e:
                # Грамотно перехватываем 429 Rate Limit
                wait_time = 30
                if e.response is not None:
                    headers = e.response.headers
                    retry_after = (
                        headers.get("retry-after")
                        or headers.get("x-ratelimit-reset")
                        or headers.get("retry-after-ms")
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

                log = f"[Subconscious] Rate Limit (429). Кулдаун ключа на {wait_time}с."
                subc_logger.warning(log)

                self.llm.rotator.cooldown_key(session.api_key, wait_time)

                if self.llm.rotator.total_keys() == 1:
                    await asyncio.sleep(wait_time + 1)
                else:
                    await asyncio.sleep(1)
                continue

            except Exception as e:
                if attempt == 4:
                    log = f"[Subconscious] LLM Ошибка: {e}"
                    subc_logger.error(log)
                    return None

                await asyncio.sleep(2)

        return None

    def _parse_response(
        self, raw_answer: str
    ) -> Tuple[Optional[AgentResponse], Optional[str]]:
        return parse_llm_json(raw_answer)

    async def _execute_actions(self, actions: List[ActionCall], pattern: Pattern) -> str:
        results = []
        for act in actions:
            # Двойная проверка RBAC (разрешен ли скилл этому паттерну)
            item = _REGISTRY.get(act.tool_name)
            if not item or pattern not in item.get("subconscious", []):
                results.append(
                    f"* Action [{act.tool_name}]: Отказано в доступе. Инструмент не разрешен для паттерна {pattern.value.upper()}."
                )
                continue

            try:
                res = await call_skill(act.tool_name, act.parameters, logger=subc_logger)
                results.append(f"* Action[{act.tool_name}]: {res.message}")
            except Exception as e:
                results.append(f"* Action[{act.tool_name}]: Внутренняя ошибка - {e}")

        return "\n".join(results)

    def _get_allowed_skills(self, pattern: Pattern) -> str:
        allowed_docs = []
        for name, data in _REGISTRY.items():
            if pattern in data.get("subconscious", []):
                allowed_docs.append(data["doc_string"])
        return "\n".join(allowed_docs) if allowed_docs else "Нет доступных инструментов."

    def _get_prompt(self, pattern: Pattern) -> str:
        prompt_path = (
            self.root_dir
            / "src"
            / "l3_agent"
            / "subconscious"
            / "prompt"
            / f"{pattern.name}.md"
        )
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8").strip()
        return f"Вы — фоновый процесс подсознания ({pattern.value.upper()})."

    def _dump_context_to_file(self, messages: list, pattern: Pattern) -> None:
        """Сохраняет промпт подсознания (Consolidation/Reflection/Forgetting) для отладки."""
        from src.utils._tools import dump_prompt_to_file

        meta = f"# SUBCONSCIOUS DUMP: {pattern.value.upper()}"
        dump_prompt_to_file(
            f"logs/prompts/{pattern.value}_prompt.md", messages, meta_header=meta
        )

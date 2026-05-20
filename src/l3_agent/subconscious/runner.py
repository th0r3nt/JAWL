import asyncio
from pathlib import Path
from typing import List, Tuple, Optional

from src.utils.logger import subc_logger

from src.l3_agent.llm.executor import LLMExecutor

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
        executor: LLMExecutor,
        model_name: str,
        sql_manager: SQLManager,
        vector_manager: VectorManager,
        graph_manager: GraphManager,
        root_dir: Path,
        max_steps: int = 4,
    ) -> None:
        self.executor = executor

        self.model_name = model_name
        self.sql = sql_manager
        self.vector = vector_manager
        self.graph = graph_manager
        self.root_dir = root_dir
        self.max_steps = max_steps

    # ========================================================
    # ОСНОВНОЙ ЦИКЛ RUN
    # ========================================================

    async def run(self, pattern: Pattern, ticks_to_analyze: int) -> None:
        """Запускает мини-цикл раздумий подсознания."""
        log = (
            f"[Subconscious] Запуск паттерна {pattern.value.upper()} (LLM: {self.model_name})."
        )
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

        # Мини-ReAct Loop
        for step in range(self.max_steps):
            await asyncio.to_thread(self._dump_context_to_file, messages, pattern)

            raw_answer = await self.executor.execute(
                model_name=self.model_name,
                messages=messages,
                temperature=0.5,
                logger=subc_logger,
                log_prefix=f"[{pattern.value.upper()}]",
                tools=ACTION_SCHEMA,
            )

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
                    f"* {act.tool_name}: Отказано в доступе. Инструмент не разрешен для паттерна {pattern.value.upper()}."
                )
                continue

            try:
                res = await call_skill(act.tool_name, act.parameters, logger=subc_logger)
                results.append(f"* {act.tool_name}: {res.message}")
            except Exception as e:
                results.append(f"* {act.tool_name}: Внутренняя ошибка - {e}")

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

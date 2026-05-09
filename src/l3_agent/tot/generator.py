"""
Генератор дерева мыслей (ToT Generator).
Оркестрирует сборку отфильтрованного контекста, вызов LLM и форматирование результата.
"""

import asyncio
import time
import openai
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.logger import main_logger, tot_logger
from src.utils.token_tracker import TokenTracker
from src.utils._tools import dump_prompt_to_file

from src.l0_state.agent.state import AgentState

from src.l1_databases.sql.management.ticks import SQLTicks

from src.l3_agent.llm.client import LLMClient
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.registry import ContextRegistry, ContextSection
from src.l3_agent.tot.schema import TOT_SCHEMA, TreeResponse, ThoughtBranch


class ToTGenerator:
    """Генератор стратегических веток."""

    def __init__(
        self,
        llm_client: LLMClient,
        model_name: str,
        prompt_builder: PromptBuilder,
        context_registry: ContextRegistry,
        agent_state: AgentState,
        sql_ticks: SQLTicks,
        token_tracker: TokenTracker,
        root_dir: Path,
        timezone: int,
        # Настройка дерева
        branches_count: int,
        simulations_per_branch: int,
        max_depth: int,
    ) -> None:
        self.llm = llm_client
        self.model_name = model_name
        self.context_registry = context_registry
        self.agent_state = agent_state
        self.sql_ticks = sql_ticks

        self.tracker = token_tracker
        self.timezone = timezone

        self.branches_count = branches_count
        self.simulations_per_branch = simulations_per_branch
        self.max_depth = max_depth

        personality_prompt = prompt_builder._gather_markdown("personality")

        prompt_path = root_dir / "src" / "l3_agent" / "tot" / "prompt" / "INSTRUCTIONS.md"
        tot_instructions = (
            prompt_path.read_text(encoding="utf-8").strip() if prompt_path.exists() else ""
        )

        self.system_prompt = f"{personality_prompt}\n\n\n{tot_instructions}".strip()

    async def generate(
        self,
        event_name: str,
        payload: Dict[str, Any],
        missed_events: List[Dict[str, Any]],
        task_description: str = "",
    ) -> Optional[str]:
        """
        Генерирует Markdown блок с деревом мыслей на основе текущей ситуации.
        """

        log = f"[Tree of Thoughts] Запуск генерации дерева мыслей (Модель: {self.model_name})."
        tot_logger.info(log)

        context = await self._build_filtered_context(event_name, payload, missed_events)

        target_focus = (
            task_description
            if task_description
            else "Провести стратегический анализ текущей ситуации и предложить оптимальные пути."
        )
        context += f"\n\n# CURRENT TASK / FOCUS \n{target_focus}"

        context += "\n\n# DIRECTIVE \n"
        context += f"1. Рекомендовано сгенерировать примерно ~{self.branches_count} макро-стратегий (веток верхнего уровня).\n"
        context += f"2. Рекомендованная глубина вложенности симуляции: ~{self.max_depth} (где макро-стратегия - 1).\n"
        context += f"3. Ветви сценарии динамически: в среднем по {self.simulations_per_branch} подварианта, но система должна сама решать, где нужно углубиться, а где ветка тупиковая или привела к логическому финалу (в таких случаях оставлять `sub_branches` пустым).\n"
        context += "4. Поля минусов и плюсов путей/сценариев необязательны. Рекомендуется заполнять их только там, где действительно имеет смысл проводить Cost-Benefit анализ.\n"

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": context},
        ]

        self.tracker.add_input_record(
            messages, log_prefix="[Tree of Thoughts LLM]", logger=tot_logger
        )
        await asyncio.to_thread(self._dump_context_to_file, messages)

        raw_json = await self._call_llm(messages)
        if not raw_json:
            return None

        try:
            parsed = TreeResponse.model_validate_json(raw_json)
            return self._format_markdown(parsed)

        except Exception as e:
            log = f"[Tree of Thoughts] Ошибка парсинга дерева мыслей: {e}"
            tot_logger.error(log)

            return None

    # ====================================================================================
    # СЛУЖЕБНЫЕ МЕТОДЫ
    # ====================================================================================

    async def _build_filtered_context(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> str:
        allowed_sections = {
            ContextSection.AGENT_STATE,
            ContextSection.DRIVES,
            ContextSection.TRAITS,
            ContextSection.MENTAL_STATES,
            ContextSection.TASKS,
            ContextSection.RAG_MEMORIES,
            ContextSection.HEARTBEAT,
        }

        all_blocks = await self.context_registry.gather_all(
            event_name=event_name,
            payload=payload,
            missed_events=missed_events,
            agent_state=self.agent_state,
        )

        filtered_blocks = []
        sorted_names = sorted(
            self.context_registry._providers.keys(),
            key=lambda k: self.context_registry._providers[k]["section"].value,
        )

        for name in sorted_names:
            section = self.context_registry._providers[name]["section"]
            if section in allowed_sections and name in all_blocks:
                filtered_blocks.append(all_blocks[name])

        # Используем стандартный get_context_block, чтобы ToT видел ту же иерархию сжатия, что и главный агент
        ticks_block = await self.sql_ticks.get_context_block()
        filtered_blocks.insert(-1, ticks_block)

        return "\n\n\n".join(filtered_blocks).strip()

    def _format_markdown(self, tree: TreeResponse) -> str:
        """
        Превращает рекурсивный объект в классическое ASCII-дерево.
        """
        if not tree.branches:
            return ""

        step = self.agent_state.current_step
        lines = [
            "## TREE OF THOUGHTS",
            "Подсознательная симуляция стратегических веток для глубокого анализа и планирования.",
            f"Время генерации: Шаг {step}\n\n```text",
        ]

        def _render_branch(
            branch: ThoughtBranch, depth: int, prefix: str, is_last: bool, indent_prefix: str
        ):
            connector = "└── " if is_last else "├── "

            # Формирование названия узла
            if depth == 0:
                node_title = f'Макро-стратегия №{prefix}: "{branch.name}"'
            elif depth == 1:
                node_title = f"Микро-симуляция №{prefix}: {branch.name}"
            else:
                node_title = f"{prefix}: {branch.name}"

            if branch.description and branch.description != branch.name:
                node_title += f" -> {branch.description}"

            lines.append(f"{indent_prefix}{connector}{node_title}")

            child_indent = indent_prefix + ("    " if is_last else "│   ")

            if branch.pros:
                pros_str = " ".join(f"[+] {p}" for p in branch.pros)
                lines.append(f"{child_indent}* Плюсы: {pros_str}")

            if branch.cons:
                cons_str = " ".join(f"[-] {c}" for c in branch.cons)
                lines.append(f"{child_indent}* Минусы: {cons_str}")

            if branch.sub_branches:
                total_subs = len(branch.sub_branches)
                for idx, sub in enumerate(branch.sub_branches):
                    new_prefix = f"{prefix}.{idx + 1}"
                    is_sub_last = idx == total_subs - 1
                    _render_branch(sub, depth + 1, new_prefix, is_sub_last, child_indent)

        total_branches = len(tree.branches)
        for i, branch in enumerate(tree.branches):
            is_last = i == total_branches - 1
            _render_branch(branch, 0, str(i + 1), is_last, "")
            if not is_last:
                lines.append("│")
                lines.append("│")

        lines.append("```")
        result = "\n".join(lines).strip()
        tot_logger.info(result)
        return result

    async def _call_llm(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        for _ in range(3):
            try:
                session = self.llm.get_session()
                response = await session.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=TOT_SCHEMA,
                )

                msg_obj = response.choices[0].message
                if msg_obj.tool_calls:
                    raw_answer = str(msg_obj.tool_calls[0].function.arguments)
                    self.tracker.add_output_record(
                        raw_answer, log_prefix="[Tree of Thoughts LLM]", logger=tot_logger
                    )
                    return raw_answer
                return None

            except RuntimeError as e:
                if "исчерпали лимиты" in str(e):
                    import re

                    match = re.search(r"подождать (\d+) сек", str(e))
                    wait_sec = int(match.group(1)) if match else 10

                    log = f"[Tree of Thoughts] Все ключи в кулдауне. Ждем {wait_sec}с."
                    tot_logger.warning(log)

                    await asyncio.sleep(wait_sec + 1)
                    continue
                return None

            except openai.RateLimitError as e:
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

                log = f"[Tree of Thoughts] Rate Limit (429). Кулдаун ключа на {wait_time}с."
                tot_logger.warning(log)

                self.llm.rotator.cooldown_key(session.api_key, wait_time)

                if self.llm.rotator.total_keys() == 1:
                    await asyncio.sleep(wait_time + 1)
                else:
                    await asyncio.sleep(1)

                continue
            except Exception as e:
                log = f"[Tree of Thoughts] LLM ошибка: {e}"
                tot_logger.error(log)

                await asyncio.sleep(2)
                continue

        return None

    def _dump_context_to_file(self, messages: List[Dict[str, Any]]) -> None:
        dump_prompt_to_file(
            "logs/prompts/tot_prompt.md", messages, meta_header="# TREE OF THOUGHTS DUMP"
        )

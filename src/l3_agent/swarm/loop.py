"""
Stateless ReAct loop for background subagents.

Unlike the main ReactLoop, subagent loops are lightweight, do not commit
events to SQLite ticks history, and run within volatile local arrays.
Enforces reporting constraints (Anti-Laziness Guard) on execution completion.
"""

import json
from typing import Dict, List, Tuple, Optional

from src.utils.logger import swarm_logger

from src.utils._tools import dump_prompt_to_file

from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.skills.schema import AgentResponse, ActionCall, ACTION_SCHEMA, parse_llm_json
from src.l3_agent.skills.registry import call_skill
from src.l3_agent.swarm.prompt.builder import SwarmPromptBuilder
from src.l3_agent.swarm.context.builder import SwarmContextBuilder
from src.l3_agent.swarm.roles import SubagentRole


class SubagentLoop:
    """Lightweight stateless reasoning loop."""

    def __init__(
        self,
        subagent_id: str,
        role: SubagentRole,
        task_description: str,
        executor: LLMExecutor,
        model_name: str,
        prompt_builder: SwarmPromptBuilder,
        context_builder: SwarmContextBuilder,
        allowed_skills: List[str],
        max_steps: int = 15,
    ) -> None:
        """
        Initializes the subagent loop.

        Args:
            subagent_id: Process UUID identifier.
            role: Dedicated worker role.
            task_description: Primary task instructions.
            executor: LLM executor instance.
            model_name: Target model name.
            prompt_builder: Swarm prompt builder.
            context_builder: Swarm context builder.
            allowed_skills: Filtered skills pool.
            max_steps: Maximum step iterations limit before force termination.
        """

        self.subagent_id = subagent_id
        self.role = role
        self.task_description = task_description

        self.executor = executor
        self.model_name = model_name
        self.prompt_builder = prompt_builder
        self.context_builder = context_builder
        self.allowed_skills = allowed_skills + ["SubagentReport.submit_final_report"]

        self.max_steps = max_steps

        self.history: List[Dict[str, str]] = []
        self.is_done = False

        self.report_submitted = False

    async def run(self) -> None:
        """
        Core subagent ReAct execution cycle.
        """

        log = f"[Swarm] Launching subagent {self.role.id}_{self.subagent_id}."
        swarm_logger.info(log)

        prompt = self.prompt_builder.build(self.role)

        step = 1
        while step <= self.max_steps and not self.is_done:
            log = f"[Subagent ReAct] Step {step}/{self.max_steps}."
            swarm_logger.info(log)

            # -----------------------------------------------------------------
            # Prompt & Context compilation
            # -----------------------------------------------------------------

            messages = self._prepare_messages(prompt)
            self._dump_context_to_file(messages, step)

            # --------------------------------------------------------------
            # LLM execution
            # --------------------------------------------------------------

            raw_answer = await self.executor.execute(
                model_name=self.model_name,
                messages=messages,
                temperature=0.7,
                logger=swarm_logger,
                log_prefix=f"[Swarm {self.subagent_id}]",
                tools=ACTION_SCHEMA,
            )
            if raw_answer is None:
                log = f"[Swarm] Critical LLM connection error on subagent {self.subagent_id}. Forcing crash report."
                swarm_logger.error(log)
                break

            # --------------------------------------------------------------
            # Response parsing
            # --------------------------------------------------------------

            parsed_response, error_msg = self._parse_response(raw_answer)

            if error_msg:
                fallback_thoughts = (
                    parsed_response if isinstance(parsed_response, str) else "[JSON Error]"
                )
                self.history.append(
                    {
                        "thoughts": fallback_thoughts,
                        "actions": "None",
                        "results": error_msg,
                    }
                )
                step += 1
                continue

            thoughts = parsed_response.thoughts
            actions = parsed_response.actions

            # --------------------------------------------------------------
            # Handle empty actions
            # --------------------------------------------------------------

            if not actions:
                if not self.report_submitted:
                    log = f"[Swarm] Subagent {self.subagent_id} attempted to exit without submitting a final report. Forcing action."
                    swarm_logger.warning(log)

                    self.history.append(
                        {
                            "thoughts": thoughts,
                            "actions": "[]",
                            "results": "[System Error]: You attempted to exit (returned an empty actions list) without submitting a final report. This is forbidden. Use the report skill to submit results.",
                        }
                    )
                    step += 1
                    continue
                else:
                    log = f"[Swarm] Subagent {self.role.id}_{self.subagent_id} returned an empty actions list. Concluding loop."
                    swarm_logger.info(log)

                    self.is_done = True
                    break

            # --------------------------------------------------------------
            # Actions execution
            # --------------------------------------------------------------

            await self._execute_and_log_actions(thoughts, actions)
            step += 1

        if not self.is_done:
            log = f"[Swarm] Subagent {self.subagent_id} reached max steps limit ({self.max_steps}) and was terminated."
            swarm_logger.warning(log)

            await call_skill(
                "SubagentReport.submit_final_report",
                {
                    "subagent_id": self.subagent_id,
                    "role": self.role.id,
                    "report": "## Timeout Error\nSubagent reached the maximum step limit and was terminated. Task incomplete.",
                },
            )

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _prepare_messages(self, prompt: str) -> List[Dict[str, str]]:
        context = self.context_builder.build(
            self.subagent_id, self.task_description, self.history
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]
        return messages

    def _dump_context_to_file(self, messages: List[Dict[str, str]], current_step: int) -> None:
        meta = f"# SUBAGENT DUMP\n* **Role**: {self.role.name.upper()}\n* **Subagent ID**: {self.subagent_id}\n* **Step**: {current_step} / {self.max_steps}"
        dump_prompt_to_file("logs/prompts/sub_prompt.md", messages, meta_header=meta)

    def _parse_response(
        self, raw_answer: str
    ) -> Tuple[Optional[AgentResponse], Optional[str]]:
        return parse_llm_json(raw_answer)

    async def _execute_and_log_actions(self, thoughts: str, actions: List[ActionCall]) -> None:
        results = []
        actions_log = []

        for act in actions:
            actions_log.append(
                f"* {act.tool_name}({json.dumps(act.parameters, ensure_ascii=False)})"
            )

            if act.tool_name not in self.allowed_skills:
                results.append(
                    f"* {act.tool_name}: Access denied. This tool is not authorized for your role."
                )
                continue

            try:
                res = await call_skill(act.tool_name, act.parameters, logger=swarm_logger)
                results.append(f"* {act.tool_name}: {res.message}")

                if act.tool_name == "SubagentReport.submit_final_report" and res.is_success:
                    self.report_submitted = True

            except Exception as e:
                results.append(f"* {act.tool_name}: Internal error - {e}")

        self.history.append(
            {
                "thoughts": thoughts,
                "actions": "\n".join(actions_log),
                "results": "\n".join(results),
            }
        )

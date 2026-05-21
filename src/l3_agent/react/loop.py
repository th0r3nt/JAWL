"""
Agent Reasoning and Acting (ReAct) Core.

Implements the Stateless loop: gathers context, sends prompt to LLM,
parses JSON outputs (Chain-of-Thought + Tool Calls), executes skills, and
commits results (Ticks) to the database.
"""

import asyncio
from typing import Dict, Any, List, Optional, Tuple

import base64
import re
import copy
from pathlib import Path

from src.utils.logger import main_logger, agent_logger
from src.utils.settings import TreeOfThoughtsConfig
from src.utils._tools import dump_prompt_to_file

from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.agent.state import AgentState, AgentStatus

from src.l1_databases.sql.management.ticks import SQLTicks
from src.l1_databases.vector.manager import VectorManager

from src.l3_agent.llm.executor import LLMExecutor
from src.l3_agent.prompt.builder import PromptBuilder
from src.l3_agent.context.builder import ContextBuilder

from src.l3_agent.tot.generator import ToTGenerator

from src.l3_agent.skills.registry import execute_skill
from src.l3_agent.skills.schema import AgentResponse, ActionCall, parse_llm_json


class ReactLoop:
    """
    Autonomous agent core.
    Implements the ReAct (Reasoning and Acting) loop in Stateless mode.
    """

    def __init__(
        self,
        executor: LLMExecutor,
        prompt_builder: PromptBuilder,
        context_builder: ContextBuilder,
        agent_state: AgentState,
        sql_ticks: SQLTicks,
        vector_manager: VectorManager,
        tools: list,
        event_bus: EventBus,
        cooldown_sec: int = 30,
        tot_config: Optional[TreeOfThoughtsConfig] = None,
        tot_generator: Optional[ToTGenerator] = None,
    ) -> None:
        """
        Initializes the ReAct loop.

        Args:
            executor: LLM executor instance.
            prompt_builder: Static system prompt compiler.
            context_builder: Context builder (manages L0 States and episodic memory).
            agent_state: Agent State L0 instance.
            sql_ticks: SQLite ticks controller.
            vector_manager: Vector DB manager.
            tools: List of available JSON schema tools.
            event_bus: Global event bus.
            cooldown_sec: Interval in seconds to wait when hitting Rate Limits (429).
            tot_config: Optional Tree of Thoughts configuration.
            tot_generator: Optional Tree of Thoughts generator.
        """

        self.executor = executor

        self.prompt_builder = prompt_builder
        self.context_builder = context_builder

        self.agent_state = agent_state

        self.sql_ticks = sql_ticks
        self.vector_manager = vector_manager

        self.tools = tools
        self.cooldown_sec = cooldown_sec

        self.event_bus = event_bus

        self.tot_config = tot_config
        self.tot_generator = tot_generator

        self.current_events: List[Dict[str, Any]] = []

    async def run(
        self, event_name: str, payload: Dict[str, Any], missed_events: List[Dict[str, Any]]
    ) -> None:
        """
        Launches the ReAct loop call to the LLM (Orchestrator).

        Args:
            event_name: Primary trigger event name.
            payload: Primary trigger event payload parameters dict.
            missed_events: List of missed background events.
        """

        self.current_events = missed_events.copy()

        try:
            self.agent_state.reset_step()

            log = f"[ReAct] Reasoning cycle initialized. Reason: {event_name} (LLM Model: {self.agent_state.llm_model})."
            agent_logger.info(log)

            prompt = self.prompt_builder.build()

            # ==================================================================
            # MAIN LOOP
            # ==================================================================

            while self.agent_state.current_step <= self.agent_state.max_react_steps:
                self.agent_state.update_state(AgentStatus.THINKING)

                # --------------------------------------------------------------
                # Tree of Thoughts generation
                # --------------------------------------------------------------

                if (
                    self.tot_config
                    and self.tot_config.enabled
                    and self.tot_config.mode in ("auto", "hybrid")
                ):
                    if (self.agent_state.current_step == 1) or (
                        (self.agent_state.current_step - 1)
                        % self.tot_config.auto_interval_steps
                        == 0
                    ):

                        tree_md = await self.tot_generator.generate(
                            event_name,
                            payload,
                            missed_events,
                            task_description="Automated thoughts tree generation to evaluate current vector.",
                        )
                        if tree_md:
                            self.agent_state.current_thoughts_tree = tree_md

                # --------------------------------------------------------------
                # Context and Prompt compilation
                # --------------------------------------------------------------

                messages = await self._prepare_messages(prompt, event_name, payload)

                # --------------------------------------------------------------
                # LLM execution call
                # --------------------------------------------------------------

                raw_answer = await self.executor.execute(
                    model_name=self.agent_state.llm_model,
                    messages=messages,
                    temperature=self.agent_state.temperature,
                    logger=agent_logger,
                    log_prefix="[LLM]",
                    tools=self.tools,
                    max_timeout_retries=1,
                )
                if raw_answer is None:
                    self.agent_state.update_state(AgentStatus.ERROR)
                    break

                # --------------------------------------------------------------
                # Response parsing
                # --------------------------------------------------------------

                parsed_response, error_msg = self._parse_response(raw_answer)
                if error_msg:
                    self.agent_state.next_step()
                    continue

                thoughts = parsed_response.thoughts.strip()
                actions = parsed_response.actions

                if thoughts:
                    log = f"[Thoughts]:\n{thoughts}\n"
                    agent_logger.info(log)

                # --------------------------------------------------------------
                # Completion checks
                # --------------------------------------------------------------

                if not actions:
                    await self._handle_completion(thoughts)
                    break

                # --------------------------------------------------------------
                # Actions execution
                # --------------------------------------------------------------

                await self._execute_actions(thoughts, actions)

                self.agent_state.next_step()

        finally:
            self.agent_state.update_state(AgentStatus.IDLE)

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    async def _prepare_messages(
        self, prompt: str, event_name: str, payload: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Assembles context, formats messages for the LLM, and injects multimodality.

        Args:
            prompt: Static system prompt.
            event_name: Primary wakeup event.
            payload: Primary wakeup payload.

        Returns:
            List[Dict[str, Any]]: Messages list in OpenAI format.
        """

        context = await self.context_builder.build(event_name, payload, self.current_events)

        if self.agent_state.current_step >= 5:
            self.current_events.clear()

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": context},
        ]

        messages = copy.deepcopy(messages)

        messages = await self._inject_images_to_payload(messages)

        self.agent_state.last_input_tokens = self.executor.tracker.count_messages_tokens(
            messages
        )

        await asyncio.to_thread(self._dump_context_to_file, messages)

        log = (
            f"[ReAct] Step {self.agent_state.current_step}/{self.agent_state.max_react_steps}."
        )
        main_logger.info(log)
        agent_logger.info(log)

        return messages

    async def _execute_actions(self, thoughts: str, actions: List[ActionCall]) -> None:
        """
        Executes requested tools, updates state, and commits results to the DB.

        Args:
            thoughts: Internal monologue (CoT).
            actions: List of actions to execute.
        """

        self.agent_state.update_state(AgentStatus.ACTING)
        results_str = await execute_skill(actions=actions)

        self.agent_state.last_thoughts = thoughts
        self.agent_state.last_actions_result = results_str

        args_to_rag = []
        for act in actions:
            for val in act.parameters.values():
                if isinstance(val, str) and len(val) > 3:
                    args_to_rag.append(val)
        self.agent_state.last_action_args = args_to_rag

        await self.sql_ticks.save_tick(
            thoughts=thoughts,
            actions=[a.model_dump() for a in actions],
            results={
                "execution_report": results_str,
                "step": self.agent_state.current_step,
                "max_steps": self.agent_state.max_react_steps,
            },
        )
        await self.event_bus.publish(Events.REACT_TICK_SAVED)

    async def _handle_completion(self, thoughts: str) -> None:
        """
        Logic for graceful completion (absence of actions).

        Args:
            thoughts: Final thoughts of the agent prior to sleep.
        """

        log = "[ReAct] Empty actions list received. Concluding cycle."
        agent_logger.info(log)

        await self.sql_ticks.save_tick(
            thoughts=thoughts,
            actions=[],
            results={
                "status": "completed",
                "step": self.agent_state.current_step,
                "max_steps": self.agent_state.max_react_steps,
            },
        )
        await self.event_bus.publish(Events.REACT_TICK_SAVED)

    def _parse_response(
        self, raw_answer: str
    ) -> Tuple[Optional[AgentResponse], Optional[str]]:
        """
        Parses the agent's JSON response.
        """
        return parse_llm_json(raw_answer)

    def add_realtime_event(self, event_data: Dict[str, Any]) -> None:
        """
        Adds an incoming event to the agent's context (called externally when the agent is awake).

        Args:
            event_data: Event payload dict.
        """

        self.current_events.append(event_data)

    def _dump_context_to_file(self, messages: List[Dict[str, Any]]) -> None:
        """
        Creates a context dump (system prompt) to a Markdown file for debugging.

        Args:
            messages: Messages array.
        """

        dump_prompt_to_file(
            "logs/prompts/main_prompt.md", messages, meta_header="# MAIN AGENT DUMP"
        )

    def _encode_image(self, image_path: str) -> str:
        """Encodes an image from disk to Base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")

    async def _inject_images_to_payload(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Injects Base64 images into the User prompt if a system marker is found.

        Args:
            messages: Messages list.

        Returns:
            List[Dict[str, Any]]: Messages list with Base64 payloads injected.
        """

        last_result = self.agent_state.last_actions_result
        if not last_result:
            return messages

        image_paths = re.findall(r"\[SYSTEM_MARKER_IMAGE_ATTACHED:\s*(.+?)\]", last_result)

        if not image_paths:
            return messages

        user_msg = messages[1]

        if isinstance(user_msg, dict) and user_msg.get("role") == "user":
            original_text = user_msg["content"]
            new_content = [{"type": "text", "text": original_text}]

            for img_path in set(image_paths):
                try:
                    path_obj = Path(img_path)
                    if path_obj.exists():
                        base64_data = await asyncio.to_thread(
                            self._encode_image, str(path_obj)
                        )
                        ext = path_obj.suffix.lower()
                        mime = "image/jpeg" if ext in [".jpg", ".jpeg"] else f"image/{ext[1:]}"

                        new_content.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime};base64,{base64_data}"},
                            }
                        )

                        log = f"[ReAct] Image {path_obj.name} successfully injected."
                        agent_logger.info(log)

                except Exception as e:
                    log = f"[ReAct] Base64 injection error: {e}"
                    main_logger.error(f"[ReAct] Base64 injection error: {e}")
                    agent_logger.error(log)

            user_msg["content"] = new_content

        return messages

"""
Skills for the agent.

These are the "hands" of the agent. Classes here contain functions decorated with `@skill()`.
Pydantic Guard Layer dynamically reads type-hints of your functions, converts them
into JSON Schema, and feeds them to the LLM model.

Quick Tip:
Do not create God Objects.

If this file grows too large (more than 200-300 lines or combines different functionality),
split it into logical subfiles in the `skills/` directory.
For example:

- `skills/messages.py` (send/read messages)
- `skills/moderation.py` (ban/mute)
- `skills/files.py` -> `skills/files/reader.py`, `skills/files/writer.py`

See the example in `src/l2_interfaces/host/os/skills/files/`.

If 1000-line files appear in this framework, the original developer will file a complaint to the Hague Tribunal (just kidding).
"""

from typing import Optional, Any

# Imports to register skills:
from src.l3_agent.skills.registry import skill, SkillResult

# If you need to restrict subagent access (RBAC):
# from src.l3_agent.swarm.roles import Subagents


class ExampleSkills:
    """Agent tools for working with custom API."""

    def __init__(self, client: Any) -> None:
        """Inject client used to make real API requests."""
        self.client = client

    # The swarm=[...] argument allows only specific subagents to call this skill.
    # If swarm is not passed, subagents will not see this skill at all. The main orchestrator always sees everything (unless hidden=True is set).

    # @skill(swarm=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    @skill()
    async def my_custom_tool(self, text_param: str, count: Optional[int] = 1) -> SkillResult:
        """
        Perfect, detailed docstring. This exact text is what the LLM will see in its System Prompt.
        Explain here what the function is for and what its arguments do.

        Args:
            text_param: Text to process.
            count: Number of iterations (default is 1).
        """

        # Pydantic Guard Layer will automatically check that `count` is an `int` (even if the LLM sends "5" as a string),
        # and if the LLM sends an array here, the function won't even launch - Guard Layer itself will return an error to the agent.

        try:
            # 1. Call the client to interact with the external world
            # response = await self.client.do_something(text_param, count)

            # 2. Log the successful action in the state history (if needed)
            # self.client.state.add_history(f"my_custom_tool called with parameter {text_param}")

            # 3. Be sure to return SkillResult.ok() on success
            return SkillResult.ok(
                f"Tool successfully executed. Text: {text_param}, count: {count}"
            )

        except Exception as e:
            # Return SkillResult.fail() with a detailed error so the agent can analyze
            # the problem in `thoughts` on the next ReAct loop step.
            return SkillResult.fail(f"Error calling external API: {e}")

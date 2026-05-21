"""
Builder of the static part of the system prompt.

Responsible for the concatenation of fragmented Markdown files (character, instructions, examples)
into a single static system prompt. Dynamic context (memory, time, logs)
is added separately in the 'context/builder.py' module.
"""

from pathlib import Path
from typing import Literal


class PromptBuilder:
    """
    Responsible for compiling the static part of the prompt (Character + Instructions + Skills).
    Dynamically filters system instructions depending on the enabled modules (YAML).
    """

    def __init__(
        self,
        prompt_dir: str | Path,
        drives_enabled: bool = False,
        tasks_enabled: bool = False,
        traits_enabled: bool = False,
        mental_states_enabled: bool = False,
        notes_enabled: bool = False,
        swarm_enabled: bool = False,
        tot_enabled: bool = False,
        subconscious_enabled: bool = False,
        hypotheses_enabled: bool = False,
    ) -> None:
        """
        Initializes the builder.

        Args:
            prompt_dir: Absolute path to the 'prompt' directory.
            drives_enabled: Whether the internal needs module is enabled.
            tasks_enabled: Whether the long-term tasks module is enabled.
            traits_enabled: Whether the personality traits module is enabled.
            mental_states_enabled: Whether the entity tracking module is enabled.
            swarm_enabled: Whether the subagents system is enabled.
            tot_enabled: Whether the strategic planning system (Tree of Thoughts) is enabled.
            hypotheses_enabled: Whether the hypotheses system is enabled.
        """

        self.prompt_dir = Path(prompt_dir)

        # Ensure system folders exist
        (self.prompt_dir / "custom").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "system" / "optional").mkdir(parents=True, exist_ok=True)

        self.drives_enabled = drives_enabled
        self.tasks_enabled = tasks_enabled
        self.traits_enabled = traits_enabled
        self.mental_states_enabled = mental_states_enabled
        self.notes_enabled = notes_enabled
        self.swarm_enabled = swarm_enabled
        self.tot_enabled = tot_enabled
        self.subconscious_enabled = subconscious_enabled
        self.hypotheses_enabled = hypotheses_enabled

    def _gather_markdown(self, sub_folder: Literal["personality", "system", "custom"]) -> str:
        """
        Recursively searches, reads, and concatenates all .md files in the specified subdirectory.
        Ignores examples (.example.md) and disables instructions for disabled modules.

        Args:
            sub_folder: Target subdirectory name.

        Returns:
            str: Concatenated content of all valid Markdown files.

        Raises:
            RuntimeError: If a prompt file cannot be read.
        """

        target_dir = self.prompt_dir / sub_folder
        if not target_dir.exists() or not target_dir.is_dir():
            return ""

        valid_files = [
            f for f in target_dir.rglob("*.md") if not f.name.endswith(".example.md")
        ]

        # Filter system modules (if they are disabled in settings)
        if not self.drives_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "DRIVES.md"]

        if not self.tasks_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "TASKS.md"]

        if not self.notes_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "NOTES.md"]

        if not self.traits_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "PERSONALITY_TRAITS.md"]

        if not self.mental_states_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "MENTAL_STATES.md"]

        if not self.swarm_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "SWARM.md"]

        if not self.tot_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "TREE_OF_THOUGHTS.md"]

        if not self.subconscious_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "SUBCONSCIOUS.md"]

        if not self.hypotheses_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "HYPOTHESES.md"]

        def sort_key(path: Path):
            name = path.name.upper()

            if name in ("SOUL.MD", "INSTRUCTIONS.MD"):
                return 0, name

            elif name in ("EXAMPLES_OF_STYLE.MD", "FUNCTION_CALL.MD"):
                return 2, name

            else:
                return 1, name

        valid_files.sort(key=sort_key)

        parts = []
        for file_path in valid_files:
            try:
                parts.append(file_path.read_text(encoding="utf-8").strip())
            except Exception as e:
                raise RuntimeError(f"Error reading prompt file {file_path}: {e}")

        return "\n\n\n".join(parts)

    def build(self) -> str:
        """
        Assembles the final system prompt.

        The order of blocks is strictly regulated:
        Character (Personality) -> Agent Custom Prompts (Custom) -> Instructions (System).

        Returns:
            str: Compiled static prompt string for the LLM.
        """

        personality = self._gather_markdown("personality")
        custom = self._gather_markdown("custom")
        system_rules = self._gather_markdown("system")

        parts = [p for p in (personality, custom, system_rules) if p]
        return "\n\n\n\n".join(parts).strip()

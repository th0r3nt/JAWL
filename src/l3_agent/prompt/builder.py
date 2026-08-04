from pathlib import Path
from typing import Literal


class PromptBuilder:
    """
    Responsible for compiling the static part of the prompt (Character + Instructions + Skills).
    Dynamically filters system instructions depending on enabled modules and language settings.
    """

    def __init__(
        self,
        prompt_dir: str | Path,
        language: str = "ru",
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
        Initializes the prompt builder.

        Args:
            prompt_dir: Absolute path to the 'prompt' directory.
            language: Target language code ('ru', 'en', etc.).
            drives_enabled: Whether the internal needs module is enabled.
            tasks_enabled: Whether the long-term tasks module is enabled.
            traits_enabled: Whether the personality traits module is enabled.
            mental_states_enabled: Whether the entity tracking module is enabled.
            notes_enabled: Whether the working memory notes module is enabled.
            swarm_enabled: Whether the subagents system is enabled.
            tot_enabled: Whether the strategic planning system (Tree of Thoughts) is enabled.
            subconscious_enabled: Whether the subconscious patterns module is enabled.
            hypotheses_enabled: Whether the hypotheses system is enabled.
        """

        self.prompt_dir = Path(prompt_dir)
        self.language = language

        # Ensure system folders exist
        (self.prompt_dir / "custom").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "system" / "optional").mkdir(parents=True, exist_ok=True)
        (self.prompt_dir / "system" / "languages").mkdir(parents=True, exist_ok=True)

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
        Ignores examples (.example.md), language files not matching active setting, and disabled modules.

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

        # Dynamic Language Filtering
        languages_dir = self.prompt_dir / "system" / "languages"
        if languages_dir.exists():
            lang_map = {
                "ru": "RUSSIAN.MD",
                "russian": "RUSSIAN.MD",
                "rus": "RUSSIAN.MD",
                "en": "ENGLISH.MD",
                "english": "ENGLISH.MD",
                "eng": "ENGLISH.MD",
            }
            target_lang_file = lang_map.get(
                self.language.lower(), f"{self.language.upper()}.MD"
            )

            valid_files = [
                f
                for f in valid_files
                if not f.is_relative_to(languages_dir) or f.name.upper() == target_lang_file
            ]

        # Filter system modules (if they are disabled in settings)
        if not self.drives_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "DRIVES.MD"]

        if not self.tasks_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "TASKS.MD"]

        if not self.notes_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "NOTES.MD"]

        if not self.traits_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "PERSONALITY_TRAITS.MD"]

        if not self.mental_states_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "MENTAL_STATES.MD"]

        if not self.swarm_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "SWARM.MD"]

        if not self.tot_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "TREE_OF_THOUGHTS.MD"]

        if not self.subconscious_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "SUBCONSCIOUS.MD"]

        if not self.hypotheses_enabled:
            valid_files = [f for f in valid_files if f.name.upper() != "HYPOTHESES.MD"]

        def sort_key(path: Path):
            name = path.name.upper()

            if name in (
                "SOUL.MD",
                "INSTRUCTIONS.MD",
                target_lang_file if languages_dir.exists() else "",
            ):
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

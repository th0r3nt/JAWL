"""
Computer vision skills of the agent (Multimodal API).

Used to convert local images/screenshots to Base64
and inject them into the prompt for models supporting Vision (e.g., gpt-4o, gemini-1.5).
"""

from src.l3_agent.skills.registry import SkillResult, skill
from src.l2_interfaces.multimodality.client import MultimodalityClient


class VisionSkills:
    """Computer vision skills of the agent."""

    def __init__(self, client: MultimodalityClient) -> None:
        self.client = client

    @skill()
    async def look_at_image(self, filepath: str) -> SkillResult:
        """
        Places system image marker.

        filepath: Relative path within `sandbox/`.
        """
        try:
            # Use secure gatekeeper from Host OS
            safe_path = self.client.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({filepath}).")

            ext = safe_path.suffix.lower()
            if ext not in [".png", ".jpg", ".jpeg", ".webp", ".gif"]:
                return SkillResult.fail(
                    f"Error: Format {ext} is not supported. Images are required."
                )

            # Return system marker
            marker = f"[SYSTEM_MARKER_IMAGE_ATTACHED: {safe_path.resolve()}]"
            return SkillResult.ok(
                f"{marker}: True. Image successfully delivered and is already in context. "
                f"[System]: It is recommended to analyze the media and save a brief description in metadata (set_file_description). "
                f"This will bind a text description to the file."
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Error trying to view media: {e}")

"""
Agent skills for transcription (Speech-to-Text).

Allow speech recognition from local media files located in the sandbox.
Include file path protection and limits on the returned text length.
"""

import asyncio

from src.utils.logger import main_logger
from src.utils._tools import format_size, truncate_text
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.host.os.client import HostOSClient
from src.l2_interfaces.voice.stt.cloud.whisper.client import CloudWhisperSTTClient


class CloudWhisperSTTTranscribation:
    """Tools for converting audio/video to text."""

    # Supported OpenAI Whisper extensions
    ALLOWED_EXTENSIONS = {".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".wav", ".webm"}

    def __init__(self, client: CloudWhisperSTTClient, host_os: HostOSClient) -> None:
        self.client = client
        self.host_os = host_os

    @skill(swarm=[Subagents.WEB_RESEARCHER, Subagents.CODER])
    async def transcribe_audio(self, filepath: str) -> SkillResult:
        """
        Extracts and transcribes speech from media file.

        filepath: Relative path within sandbox/.
        """
        try:
            # 1. Validate path via gatekeeper
            safe_path = self.host_os.validate_path(filepath, is_write=False)

            if not safe_path.is_file():
                return SkillResult.fail(f"Error: File not found ({safe_path.name}).")

            ext = safe_path.suffix.lower()
            if ext not in self.ALLOWED_EXTENSIONS:
                return SkillResult.fail(
                    f"Error: Extension '{ext}' is not supported. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"
                )

            size_bytes = safe_path.stat().st_size
            if size_bytes == 0:
                return SkillResult.fail("Error: File is empty.")

            # OpenAI API has a 25 MB limit
            if size_bytes > 25 * 1024 * 1024:
                return SkillResult.fail(
                    f"Error: File size ({format_size(size_bytes)}) exceeds API limit (25 MB)."
                )

            main_logger.info(
                f"[Cloud Whisper STT] Starting transcription: {safe_path.name} ({format_size(size_bytes)})..."
            )

            # 2. Read bytes from disk asynchronously
            def _read_bytes() -> bytes:
                with open(safe_path, "rb") as f:
                    return f.read()

            file_bytes = await asyncio.to_thread(_read_bytes)
            file_tuple = (safe_path.name, file_bytes)

            # 3. Send to API
            text = await self.client.transcribe(file_tuple)

            if not text.strip():
                return SkillResult.ok("No recognizable speech found in the file (or silence).")

            # 4. Truncate text to protect LLM context (maximum ~15k characters)
            clean_text = truncate_text(
                text.strip(),
                15000,
                suffix="\n... [Transcription truncated: character limit exceeded]",
            )

            # 5. Log in state history
            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()
            self.client.state.add_history(
                f"Transcribed '{rel_path}' ({format_size(size_bytes)})"
            )

            return SkillResult.ok(
                f"Transcription result of '{safe_path.name}':\n\n{clean_text}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except RuntimeError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            main_logger.error(f"[Cloud Whisper STT] Error during transcription: {e}")
            return SkillResult.fail(f"API error during transcription: {e}")

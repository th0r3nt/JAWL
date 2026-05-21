"""
Agent skills for speech synthesis via Microsoft Edge TTS.
"""

import uuid
from typing import Optional

from src.utils._tools import format_size
from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.voice.tts.cloud.edge.client import EdgeClient
from src.l2_interfaces.host.os.client import HostOSClient


class EdgeTTSGeneration:
    """Edge TTS speech generation tools."""

    def __init__(self, client: EdgeClient, host_os: HostOSClient) -> None:
        """
        Args:
            client: Edge TTS client.
            host_os: Gatekeeper for secure resolution of save paths.
        """

        self.client = client
        self.host_os = host_os

    @skill(swarm=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    async def get_available_voices(self) -> SkillResult:
        """
        Returns available voices.
        """

        voices = self.client.state.available_voices_cache
        if not voices:
            return SkillResult.fail(
                "Voice cache is empty. Possible network loss or interface is offline."
            )

        return SkillResult.ok("Available Edge TTS voices:\n- " + "\n- ".join(voices))

    @skill()
    async def generate_speech(
        self, text: str, voice_id: Optional[str] = None, filename: Optional[str] = None
    ) -> SkillResult:
        """
        Synthesizes and saves speech.

        filename: Output .mp3 name.
        """

        if not text.strip():
            return SkillResult.fail("Text for voiceover cannot be empty.")

        v_id = voice_id if voice_id else self.client.voice_manager.main_voice
        f_name = filename if filename else f"edge_speech_{uuid.uuid4().hex[:8]}.mp3"

        # Route by default to the sandbox system downloads folder
        if "/" not in f_name and "\\" not in f_name:
            f_name = f"sandbox/_system/download/{f_name}"

        try:
            # Safely resolve the path via gatekeeper
            safe_path = self.host_os.validate_path(f_name, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            main_logger.info(
                f"[Edge TTS] Speech generation started (Voice: {v_id}, File: {safe_path.name})"
            )

            # Invoke asynchronous generation
            await self.client.generate_audio(text=text, voice=v_id, output_path=str(safe_path))

            # Format logs
            size_str = format_size(safe_path.stat().st_size)
            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()

            self.client.state.add_history(
                f"Generated {rel_path} (size: {size_str}, text: {text})"
            )

            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except RuntimeError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            main_logger.error(f"[Edge TTS] Generation error: {e}")
            return SkillResult.fail(f"Speech generation API error (Edge): {e}")

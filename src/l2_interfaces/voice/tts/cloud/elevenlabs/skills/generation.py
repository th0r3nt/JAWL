"""
Agent skills for speech synthesis.
"""

import uuid
import asyncio
from src.utils._tools import format_size
from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l3_agent.swarm.roles import Subagents

from src.l2_interfaces.voice.tts.cloud.elevenlabs.client import CloudElevenLabsTTSClient
from src.l2_interfaces.host.os.client import HostOSClient


class CloudElevenLabsTTSGeneration:
    """Speech generation tools."""

    def __init__(self, client: CloudElevenLabsTTSClient, host_os: HostOSClient):
        self.client = client
        self.host_os = host_os

    @skill(swarm=[Subagents.CODER, Subagents.WEB_RESEARCHER])
    async def get_available_voices(self) -> SkillResult:
        """
        Returns available voices and their IDs.
        """

        voices = self.client.state.available_voices_cache
        if not voices:
            return SkillResult.fail(
                "Voice cache is empty. Perhaps the interface is not initialized."
            )

        return SkillResult.ok("Available voices:\n- " + "\n- ".join(voices))

    @skill()
    async def generate_speech(
        self, text: str, voice_id: str = None, filename: str = None
    ) -> SkillResult:
        """
        Synthesizes speech from text.

        voice_id: Optional voice ID.
        filename: Optional output filename.
        """
        if not text.strip():
            return SkillResult.fail("Text for voiceover cannot be empty.")

        v_id = voice_id if voice_id else self.client.voice_manager.main_voice
        f_name = filename if filename else f"speech_{uuid.uuid4().hex[:8]}.mp3"

        if "/" not in f_name and "\\" not in f_name:
            f_name = f"sandbox/_system/download/{f_name}"

        try:
            # Safely resolve the path via gatekeeper
            safe_path = self.host_os.validate_path(f_name, is_write=True)
            safe_path.parent.mkdir(parents=True, exist_ok=True)

            body = {
                "text": text,
                "model_id": self.client.voice_manager.model_id,
                "voice_settings": self.client.voice_manager.get_voice_settings(),
            }

            main_logger.info(
                f"[ElevenLabs] Speech generation started (Voice: {v_id}, File: {safe_path.name})"
            )

            binary_audio = await self.client.request(
                "POST", f"/text-to-speech/{v_id}", body=body, binary=True
            )

            def _save():
                safe_path.write_bytes(binary_audio)

            await asyncio.to_thread(_save)

            # Update quota in state asynchronously to not block the agent
            asyncio.create_task(self.client.update_quota())

            size_str = format_size(safe_path.stat().st_size)
            rel_path = safe_path.relative_to(self.host_os.sandbox_dir).as_posix()

            self.client.state.add_history(
                f"Generated {rel_path} (size: {size_str}, text: {text})"
            )

            return SkillResult.ok("True")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            main_logger.error(f"[ElevenLabs] Generation error: {e}")
            return SkillResult.fail(f"Speech generation API error: {e}")

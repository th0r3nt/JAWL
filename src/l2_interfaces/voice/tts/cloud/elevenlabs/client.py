"""
Stateful client for working with ElevenLabs API.

Performs low-level HTTP requests and bypasses Cloudflare protection (via User-Agent).
"""

import json
import urllib.request
import urllib.error
import asyncio
from typing import Any

from src.utils.logger import main_logger
from src.l2_interfaces.voice.tts.cloud.elevenlabs.state import CloudElevenLabsTTSState
from src.l2_interfaces.voice.tts.cloud.elevenlabs.voices import VoiceManager


class CloudElevenLabsTTSClient:
    """ElevenLabs HTTP connection manager."""

    def __init__(
        self,
        state: CloudElevenLabsTTSState,
        voice_manager: VoiceManager,
        api_key: str,
        api_url: str,
    ):
        self.state = state
        self.voice_manager = voice_manager
        self.api_key = api_key
        self.api_url = api_url.rstrip("/")

        # Bypassing Cloudflare protection (1010) that default python user-agents run into
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    async def start(self) -> None:
        """
        Lifecycle method. Validates token and pulls quotas.
        """

        try:
            # 1. Verify account quota
            user_data = await self.request("GET", "/user")
            sub = user_data.get("subscription", {})
            self.state.character_count = sub.get("character_count", 0)
            self.state.character_limit = sub.get("character_limit", 0)

            # 2. Cache available voices
            voices_data = await self.request("GET", "/voices")
            for v in voices_data.get("voices", []):
                # If a list is strictly specified in config - filter, otherwise take everything
                if (
                    not self.voice_manager.allowed_voices
                    or v["voice_id"] in self.voice_manager.allowed_voices
                ):
                    self.state.available_voices_cache.append(
                        f"{v['name']} (ID: {v['voice_id']})"
                    )

            self.state.is_online = True
            main_logger.info(
                "[ElevenLabs] TTS interface started. Connection with API established."
            )

        except Exception as e:
            main_logger.error(f"[ElevenLabs] Initialization error: {e}")
            self.state.is_online = False

    async def stop(self) -> None:
        self.state.is_online = False

    async def update_quota(self) -> None:
        """
        Asynchronously updates remaining characters.
        """
        try:
            user_data = await self.request("GET", "/user")
            sub = user_data.get("subscription", {})
            self.state.character_count = sub.get("character_count", 0)
        except Exception:
            pass

    async def request(
        self, method: str, endpoint: str, body: dict = None, binary: bool = False
    ) -> Any:
        """Low-level asynchronous HTTP request."""

        def _do_request():
            url = f"{self.api_url}/{endpoint.lstrip('/')}"
            headers = {
                "User-Agent": self.user_agent,
                "xi-api-key": self.api_key,
                "Accept": "audio/mpeg" if binary else "application/json",
            }

            data_bytes = None
            if body:
                data_bytes = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"

            req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)

            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    if binary:
                        return resp.read()
                    return json.loads(resp.read().decode("utf-8"))

            except urllib.error.HTTPError as e:
                err_msg = e.read().decode("utf-8", errors="ignore")
                raise Exception(f"HTTP {e.code}: {err_msg}")

        return await asyncio.to_thread(_do_request)

    async def get_context_block(self, **kwargs: Any) -> str:
        """
        Formats the state block for the agent system prompt.
        """

        desc = "Description: Text-to-Speech generation via ElevenLabs API."
        if not self.state.is_online:
            return f"### ELEVENLABS TTS [OFF]\n{desc}\nThe interface is disabled."

        used = self.state.character_count
        limit = self.state.character_limit

        # Attempt to find name of the main voice
        main_voice_id = self.voice_manager.main_voice
        main_voice_str = main_voice_id  # Fallback if not found in cache

        for v_str in self.state.available_voices_cache:
            if main_voice_id in v_str:
                main_voice_str = v_str
                break

        # Format available voices list
        voices_cache = self.state.available_voices_cache
        if not voices_cache:
            available_str = "  Cache is empty."
        elif len(voices_cache) > 5:
            # Show top 5, hide the rest under a skill
            display_voices = voices_cache[:5]
            available_str = "\n".join(f"  - {v}" for v in display_voices)
            available_str += f"\n  ...and another {len(voices_cache) - 5} voices."
        else:
            available_str = "\n".join(f"  - {v}" for v in voices_cache)

        return f"""### ELEVENLABS TTS [ON]
{desc}
* Quota: {used}/{limit} characters. 

* Main voice (default): {main_voice_str}
* Available voices:
{available_str}

* Generation history:
{self.state.recent_history}
"""

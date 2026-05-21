"""
Background HTTP server based on aiohttp (Webhook Receiver).

Listens to a dedicated local port and intercepts POST/GET requests from external integrations
(GitHub Actions, Stripe, Smart Home), forwarding their payload (JSON) to the agent's EventBus.
Protected by a token validation mechanism.
"""

import hmac
import json
import uuid
from typing import Optional
from aiohttp import web

from src.utils.logger import main_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.dtime import get_now_formatted

from src.l2_interfaces.web.hooks.state import WebHooksState
from src.l2_interfaces.web.hooks.client import WebHooksClient


class WebHooksEvents:
    """Background worker: launches aiohttp server to receive webhooks."""

    def __init__(
        self, client: WebHooksClient, state: WebHooksState, event_bus: EventBus, timezone: int
    ) -> None:
        self.client = client
        self.state = state
        self.bus = event_bus
        self.timezone = timezone

        self.app = web.Application()

        # Universal funnel endpoint
        self.app.router.add_post("/webhook/{source}", self.handle_webhook)
        self.app.router.add_get("/webhook/{source}", self.handle_webhook)  # Just in case

        self.runner: Optional[web.AppRunner] = None

    async def start(self) -> None:
        """Starts the webhook server."""
        if self.state.is_online:
            return

        if not self.client.secret_token:
            main_logger.error(
                "[Web Hooks] WEBHOOK_SECRET is not set in .env. Server not started."
            )
            return

        try:
            self.runner = web.AppRunner(self.app, access_log=None)
            await self.runner.setup()
            size = web.TCPSite(self.runner, self.client.config.host, self.client.config.port)
            await size.start()

            self.state.is_online = True
            main_logger.info(
                f"[Web Hooks] Server started at http://{self.client.config.host}:{self.client.config.port}"
            )

        except Exception as e:
            main_logger.error(f"[Web Hooks] Server startup error: {e}")

            # Clean up if port binding failed
            if self.runner:
                await self.runner.cleanup()
                self.runner = None

    async def stop(self) -> None:
        """Stops the webhook server."""
        self.state.is_online = False
        if self.runner:
            await self.runner.cleanup()
            main_logger.info("[Web Hooks] Server stopped.")

    async def handle_webhook(self, request: web.Request) -> web.Response:
        """
        Universal funnel endpoint.
        Validates token (Query or Bearer), parses body (JSON or Text), and generates
        a WEBHOOK_MESSAGE_INCOMING event to urgently wake up the Heartbeat.

        Args:
            request: Incoming HTTP request (aiohttp).

        Returns:
            web.Response: 200 OK or 401 Unauthorized.
        """
        # Token validation
        token = request.query.get("token")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "").strip()

        # hmac.compare_digest — protection against timing attacks. Normal != stops comparison
        # at the first mismatched character, and the response time difference allows the attacker
        # to guess the secret character by character. compare_digest always compares in constant time.
        if not self.client.secret_token or not hmac.compare_digest(
            token or "", self.client.secret_token
        ):
            main_logger.warning(
                f"[Web Hooks] Unauthorized access attempt from IP {request.remote} (incoming token is invalid)"
            )
            return web.json_response(
                {"status": "error", "message": "Unauthorized"}, status=401
            )

        # Getting data
        source = request.match_info.get("source", "unknown")

        try:
            payload = await request.json()
            is_json = True
        except json.JSONDecodeError:
            payload = await request.text()
            is_json = False

        # Updating L0 state
        hook_id = str(uuid.uuid4())[:8]
        time_str = get_now_formatted(self.timezone, "%H:%M:%S")

        # Create short preview for the prompt
        raw_str = json.dumps(payload, ensure_ascii=False) if is_json else str(payload)
        preview = raw_str.replace("\n", " ").strip()

        limit = self.client.config.preview_max_chars
        if len(preview) > limit:
            preview = preview[:limit] + "... [Truncated]"

        self.state.add_hook(hook_id, source, time_str, payload, preview)
        main_logger.info(f"[Web Hooks] Webhook received from '{source}' (ID: {hook_id})")

        # Forward event to the agent core
        await self.bus.publish(
            Events.WEBHOOK_MESSAGE_INCOMING,
            source=source,
            hook_id=hook_id,
            message=f"New webhook from {source}",
            preview=preview,
        )

        return web.json_response({"status": "ok", "id": hook_id})

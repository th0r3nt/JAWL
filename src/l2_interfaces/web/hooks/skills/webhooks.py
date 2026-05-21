import json

from src.utils.logger import main_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.hooks.client import WebHooksClient


class WebHooksSkills:
    """Skills for working with incoming HTTP webhooks."""

    def __init__(self, client: WebHooksClient):
        self.client = client

    @skill()
    async def read_webhook_payload(self, hook_id: str) -> SkillResult:
        """
        Reads full payload of inbound webhook.
        """

        for hook in self.client.state.recent_hooks:
            if hook["id"] == hook_id:
                payload = hook["payload"]

                if isinstance(payload, dict):
                    formatted_payload = json.dumps(payload, ensure_ascii=False, indent=2)
                    result_text = f"Full payload of webhook `{hook_id}`:\n```json\n{formatted_payload}\n```"
                else:
                    result_text = (
                        f"Full payload of webhook `{hook_id}`:\n```text\n{payload}\n```"
                    )

                main_logger.info(f"[Web Hooks] Full payload read for webhook: {hook_id}")
                return SkillResult.ok(result_text)

        return SkillResult.fail(
            f"Webhook with ID '{hook_id}' not found. It might have expired and been removed from history."
        )

    @skill()
    async def clear_webhooks_history(self) -> SkillResult:
        """
        Clears inbound webhook history in system prompt.
        """

        count = len(self.client.state.recent_hooks)
        self.client.state.recent_hooks.clear()
        self.client.state.preview_lines.clear()

        main_logger.info(f"[Web Hooks] History cleared ({count} records deleted).")
        return SkillResult.ok("True")

    @skill()
    async def get_webhooks_by_source(self, source: str) -> SkillResult:
        """
        Returns webhooks filtered by source.
        """

        filtered = [
            h for h in self.client.state.recent_hooks if h["source"].lower() == source.lower()
        ]

        if not filtered:
            return SkillResult.ok(f"No webhooks from source '{source}' found.")

        lines = [f"Found {len(filtered)} records from '{source}':"]
        for h in filtered:
            # Search preview for this record in preview_lines (by ID)
            preview = next(
                (p for p in self.client.state.preview_lines if f"`{h['id']}`" in p),
                "No preview available",
            )
            lines.append(preview)

        return SkillResult.ok("\n".join(lines))

import json

from src.utils.logger import system_logger
from src.l3_agent.skills.registry import skill, SkillResult
from src.l2_interfaces.web.hooks.client import WebHooksClient


class WebHooksSkills:
    """Навыки для работы с входящими HTTP-вебхуками."""

    def __init__(self, client: WebHooksClient):
        self.client = client

    @skill()
    async def read_webhook_payload(self, hook_id: str) -> SkillResult:
        """
        Читает полную полезную нагрузку (payload) входящего вебхука по его ID.
        """
        for hook in self.client.state.recent_hooks:
            if hook["id"] == hook_id:
                payload = hook["payload"]

                if isinstance(payload, dict):
                    formatted_payload = json.dumps(payload, ensure_ascii=False, indent=2)
                    result_text = f"Полные данные вебхука `{hook_id}`:\n```json\n{formatted_payload}\n```"
                else:
                    result_text = (
                        f"Полные данные вебхука `{hook_id}`:\n```text\n{payload}\n```"
                    )

                system_logger.info(f"[Web Hooks] Прочитаны полные данные вебхука: {hook_id}")
                return SkillResult.ok(result_text)

        return SkillResult.fail(
            f"Вебхук с ID '{hook_id}' не найден. Возможно, он устарел и был удален из истории."
        )

    @skill()
    async def clear_webhooks_history(self) -> SkillResult:
        """
        Полностью очищает историю входящих вебхуков в контексте.
        """

        count = len(self.client.state.recent_hooks)
        self.client.state.recent_hooks.clear()
        self.client.state.preview_lines.clear()

        system_logger.info(f"[Web Hooks] История очищена ({count} записей удалено).")
        return SkillResult.ok(f"История вебхуков успешно очищена. Удалено {count} записей.")

    @skill()
    async def get_webhooks_by_source(self, source: str) -> SkillResult:
        """
        Возвращает список вебхуков, отфильтрованных по источнику.
        """

        filtered = [
            h for h in self.client.state.recent_hooks if h["source"].lower() == source.lower()
        ]

        if not filtered:
            return SkillResult.ok(f"Вебхуков от источника '{source}' не обнаружено.")

        lines = [f"Найдено {len(filtered)} записей от '{source}':"]
        for h in filtered:
            # Ищем превью для этой записи в preview_lines (по ID)
            preview = next(
                (p for p in self.client.state.preview_lines if f"`{h['id']}`" in p),
                "Нет превью",
            )
            lines.append(preview)

        return SkillResult.ok("\n".join(lines))

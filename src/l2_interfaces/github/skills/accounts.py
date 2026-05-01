"""
Навыки агента для работы с профилями и уведомлениями GitHub.
"""

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class GithubAccounts:
    """Навыки для работы с профилями и уведомлениями."""

    def __init__(self, client: GithubClient) -> None:
        self.client = client

    @skill()
    async def get_user_profile(self, username: str) -> SkillResult:
        """
        Возвращает публичный профиль пользователя GitHub.

        Args:
            username: Никнейм пользователя на GitHub.
        """
        try:
            data = await self.client.request("GET", f"/users/{username}")
            self.client.state.add_history(f"get_user: {username}")

            if not isinstance(data, dict):
                return SkillResult.fail("Не удалось распарсить профиль.")

            lines = [
                f"Пользователь: {data.get('login')} ({data.get('name', 'Без имени')})",
                f"Био: {data.get('bio', 'Пусто')}",
                f"Публичных реп: {data.get('public_repos')} | Gists: {data.get('public_gists')}",
                f"Подписчиков: {data.get('followers')} | Подписок: {data.get('following')}",
                f"Компания: {data.get('company', 'Нет')} | Локация: {data.get('location', 'Нет')}",
            ]
            system_logger.info(f"[Github] Прочитан профиль пользователя {username}")
            return SkillResult.ok("\n".join(lines))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении профиля: {e}")

    @skill()
    async def get_my_notifications(self, unread_only: bool = True) -> SkillResult:
        """
        [Требует Agent Account] Проверяет входящие уведомления агента (меншны, ревью).

        Args:
            unread_only: Если True, вернет только новые непрочитанные.
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для проверки уведомлений нужен Agent Account.")

        try:
            query = "?all=false" if unread_only else "?all=true"
            data = await self.client.request("GET", f"/notifications{query}")
            self.client.state.add_history("get_notifications")

            if not data or not isinstance(data, list):
                return SkillResult.ok("Новых уведомлений нет.")

            lines = ["Ваши последние уведомления:"]
            for n in data[:15]:  # Лимит 15
                repo = (n.get("repository") or {}).get("full_name", "Unknown")
                subject = n.get("subject", {})
                title = subject.get("title", "No title")
                n_type = subject.get("type", "Unknown")
                reason = n.get("reason", "unknown")
                lines.append(f"- [{repo}] {n_type}: '{title}' (Причина: {reason})")

            system_logger.info(f"[Github] Проверены уведомления (Найдено: {len(data)})")
            return SkillResult.ok("\n".join(lines))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при проверке уведомлений: {e}")

    @skill()
    async def mark_notifications_as_read(self) -> SkillResult:
        """
        [Требует Agent Account] Помечает все текущие непрочитанные уведомления как прочитанные.
        Полезно вызывать после их прочтения, чтобы очистить инбокс.
        """
        
        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для этого действия нужен Agent Account.")

        try:
            # PUT /notifications помечает все уведомления прочитанными
            await self.client.request("PUT", "/notifications")
            self.client.state.add_history("mark_notifications_read")

            # Мгновенно очищаем дашборд агента, не дожидаясь следующего тика фонового поллинга
            self.client.state.unread_notifications = "Нет новых уведомлений."

            system_logger.info("[Github] Все уведомления агента помечены как прочитанные.")
            return SkillResult.ok(
                "Все уведомления успешно помечены как прочитанные (инбокс очищен)."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при очистке уведомлений: {e}")

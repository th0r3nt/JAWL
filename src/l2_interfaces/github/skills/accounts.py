from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class GithubAccounts:
    """Навыки для работы с профилями и уведомлениями."""

    def __init__(self, client: GithubClient):
        self.client = client

    @skill()
    async def get_user_profile(self, username: str) -> SkillResult:
        """
        Возвращает публичный профиль пользователя GitHub.
        """

        try:
            data = await self.client.request("GET", f"/users/{username}")
            self.client.state.add_history(f"get_user: {username}")

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
        """

        if not self.client.config.agent_account:
            return SkillResult.fail("Ошибка: Для проверки уведомлений нужен Agent Account.")

        try:
            query = "?all=false" if unread_only else "?all=true"
            data = await self.client.request("GET", f"/notifications{query}")
            self.client.state.add_history("get_notifications")

            if not data:
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

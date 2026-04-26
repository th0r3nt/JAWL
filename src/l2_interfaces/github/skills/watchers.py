from src.l2_interfaces.github.client import GithubClient
from src.l2_interfaces.github.events import GithubEvents
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger


class GithubWatchers:
    """Навыки для отслеживания событий в чужих или своих репозиториях."""

    def __init__(self, client: GithubClient, events: GithubEvents):
        self.client = client
        self.events = events

    @skill()
    async def track_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Начинает отслеживание активности в указанном репозитории (коммиты, issues, PR).
        """

        repo_name = f"{owner}/{repo}"

        if repo_name in self.client.state.tracked_repos:
            return SkillResult.ok(f"Репозиторий {repo_name} уже отслеживается.")

        try:
            # Делаем тестовый запрос
            await self.client.request("GET", f"/repos/{owner}/{repo}")

            # Подписка на Гитхабе (чтобы появиться в списке Watchers на сайте)
            if self.client.config.agent_account and self.client.token:
                try:
                    await self.client.request(
                        "PUT", f"/repos/{owner}/{repo}/subscription", body={"subscribed": True}
                    )
                except Exception as sub_err:
                    system_logger.debug(
                        f"[Github] Не удалось физически подписаться на {repo_name}: {sub_err}"
                    )

            self.client.state.tracked_repos[repo_name] = ""
            self.events.save_persisted_repos()

            system_logger.info(f"[Github] Начато отслеживание репозитория: {repo_name}")
            return SkillResult.ok(f"Успешно. Репозиторий {repo_name} добавлен в Watchers.")

        except Exception as e:
            return SkillResult.fail(
                f"Ошибка при добавлении в отслеживаемые (репозиторий не найден?): {e}"
            )

    @skill()
    async def untrack_repository(self, owner: str, repo: str) -> SkillResult:
        """
        Прекращает отслеживание репозитория.
        """

        repo_name = f"{owner}/{repo}"

        if repo_name not in self.client.state.tracked_repos:
            return SkillResult.fail(f"Ошибка: Репозиторий {repo_name} не отслеживался.")

        del self.client.state.tracked_repos[repo_name]
        self.events.save_persisted_repos()

        # Отписываемся на самом сайте
        if self.client.config.agent_account and self.client.token:
            try:
                await self.client.request("DELETE", f"/repos/{owner}/{repo}/subscription")
            except Exception:
                pass

        system_logger.info(f"[Github] Прекращено отслеживание репозитория: {repo_name}")
        return SkillResult.ok(f"Успешно. Репозиторий {repo_name} удален из Watchers.")

    @skill()
    async def get_tracked_repositories(self) -> SkillResult:
        """
        Возвращает список отслеживаемых репозиториев.
        """

        tracked = list(self.client.state.tracked_repos.keys())

        if not tracked:
            return SkillResult.ok("Список отслеживаемых репозиториев пуст.")

        return SkillResult.ok("Отслеживаемые репозитории:\n- " + "\n- ".join(tracked))

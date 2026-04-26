import asyncio
import json
from pathlib import Path
from typing import Optional

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events

from src.l0_state.interfaces.state import GithubState
from src.l2_interfaces.github.client import GithubClient


class GithubEvents:
    """
    Фоновый мониторинг GitHub (Уведомления аккаунта + Watchers).
    """

    def __init__(
        self, client: GithubClient, state: GithubState, event_bus: EventBus, data_dir: Path
    ):
        self.client = client
        self.state = state
        self.bus = event_bus
        self.data_dir = data_dir

        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

        self._persistence_file = self.data_dir / "github" / "tracked_repos.json"
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        if self._is_running:
            return

        self._load_persisted_repos()
        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info("[Github] Фоновый поллинг запущен.")

    async def stop(self) -> None:
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        system_logger.info("[Github] Фоновый поллинг остановлен.")

    # ==========================================================
    # PERSISTENCE (Сохранение на диск)
    # ==========================================================

    def _load_persisted_repos(self):
        if not self._persistence_file.exists():
            return
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.state.tracked_repos = data
        except Exception as e:
            system_logger.warning(f"[Github] Ошибка чтения tracked_repos.json: {e}")

    def save_persisted_repos(self):
        try:
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.state.tracked_repos, f, indent=4)
        except Exception as e:
            system_logger.error(f"[Github] Ошибка сохранения tracked_repos.json: {e}")

    # ==========================================================
    # POLLING LOOP
    # ==========================================================

    async def _loop(self):
        """
        Единый цикл для обновления профиля и отслеживаемых реп.
        """

        while self._is_running:
            try:
                # 1. Обновляем дашборд аккаунта (если включено)
                if self.client.config.agent_account and self.client.token:
                    await self._poll_account_state()

                # 2. Опрашиваем отслеживаемые репозитории
                if self.state.tracked_repos:
                    await self._poll_watched_repos()

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.debug(f"[Github] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.client.config.polling_interval_sec)

    async def _poll_account_state(self):
        """
        Собирает дашборд.
        """

        try:
            repos_data = await self.client.request(
                "GET", "/user/repos", params={"sort": "updated", "per_page": 5}
            )
            if repos_data and isinstance(repos_data, list):
                repo_lines = []
                for r in repos_data:
                    name = r.get("full_name")
                    stars = r.get("stargazers_count", 0)
                    is_fork = " (Fork)" if r.get("fork") else ""
                    repo_lines.append(f"- {name}{is_fork} ({stars}⭐)")
                self.state.own_repos = (
                    "\n".join(repo_lines) if repo_lines else "У вас пока нет репозиториев."
                )

            notif_data = await self.client.request(
                "GET", "/notifications", params={"all": "false"}
            )
            if isinstance(notif_data, list):
                count = len(notif_data)
                if count == 0:
                    self.state.unread_notifications = "Нет новых уведомлений."
                else:
                    notif_lines = [f"У вас {count} непрочитанных уведомлений:"]
                    for n in notif_data[:3]:
                        title = n.get("subject", {}).get("title", "No title")
                        repo = (n.get("repository") or {}).get("full_name", "Unknown")
                        n_type = n.get("subject", {}).get("type", "Unknown")
                        notif_lines.append(f"- [{repo}] {n_type}: {title}")
                    self.state.unread_notifications = "\n".join(notif_lines)

        except Exception as e:
            system_logger.debug(f"[Github] Ошибка фонового обновления профиля: {e}")

    async def _poll_watched_repos(self):
        """Опрашивает /events для каждого отслеживаемого репозитория."""

        modified = False

        for repo_name, last_event_id in list(self.state.tracked_repos.items()):
            try:
                # Увеличили лимит до 30, чтобы мусорные ивенты не вытеснили пуши
                events_data = await self.client.request(
                    "GET", f"/repos/{repo_name}/events", params={"per_page": 30}
                )

                if not isinstance(events_data, list) or not events_data:
                    continue

                events_data.reverse()

                is_initial_load = not bool(last_event_id)
                needs_dashboard_fill = len(self.state.recent_watcher_events) == 0

                highest_parsed_id = last_event_id

                for event in events_data:
                    event_id = str(event.get("id"))
                    if not event_id:
                        continue

                    try:
                        is_new = int(event_id) > int(last_event_id) if last_event_id else True
                    except (ValueError, TypeError):
                        is_new = event_id > str(last_event_id)

                    parsed_msg = self._parse_github_event(event)

                    # Если событие неинтересное (звезда, форк) - мы не обновляем ватермарку ID
                    # Это решает проблему GitHub Eventual Consistency
                    if not parsed_msg:
                        continue

                    if is_initial_load:
                        self.state.add_watcher_event(parsed_msg)
                        highest_parsed_id = event_id
                        continue

                    if not is_new:
                        if (
                            needs_dashboard_fill
                            and parsed_msg not in self.state.recent_watcher_events
                        ):
                            self.state.add_watcher_event(parsed_msg)
                        continue

                    # НОВОЕ ЗНАЧИМОЕ СОБЫТИЕ
                    self.state.add_watcher_event(parsed_msg)
                    await self.bus.publish(
                        Events.GITHUB_REPO_ACTIVITY, repo=repo_name, message=parsed_msg
                    )

                    # Обновляем ID только по значимым событиям
                    try:
                        if (
                            int(event_id) > int(highest_parsed_id)
                            if highest_parsed_id
                            else True
                        ):
                            highest_parsed_id = event_id
                    except (ValueError, TypeError):
                        highest_parsed_id = event_id

                if highest_parsed_id != last_event_id:
                    self.state.tracked_repos[repo_name] = highest_parsed_id
                    modified = True

            except Exception as e:
                system_logger.debug(f"[Github] Ошибка поллинга репозитория {repo_name}: {e}")

        if modified:
            self.save_persisted_repos()

    def _parse_github_event(self, event: dict) -> Optional[str]:
        """
        Превращает JSON Github Event в читаемую строку. Игнорирует мусорные события.
        """

        event_type = event.get("type")
        actor = event.get("actor", {}).get("login", "Unknown")
        repo = event.get("repo", {}).get("name", "Unknown")
        payload = event.get("payload", {})

        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            # Надежный подсчет коммитов
            count = payload.get("size", len(commits))

            if count == 0:
                return None

            msg = commits[0].get("message", "").split("\n")[0] if commits else "Без описания"
            return f"[{repo}] 🔨 @{actor} запушил {count} коммит(ов). Последний: '{msg}'"

        elif event_type == "IssuesEvent":
            action = payload.get("action")
            if action not in ("opened", "closed", "reopened", "commented"):
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            title = payload.get("issue", {}).get("title", "")
            return f"[{repo}] 📝 @{actor} {action} issue #{issue_num}: '{title}'"

        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr_num = payload.get("pull_request", {}).get("number", "?")
            title = payload.get("pull_request", {}).get("title", "")
            return f"[{repo}] 🔀 @{actor} {action} Pull Request #{pr_num}: '{title}'"

        elif event_type == "IssueCommentEvent":
            action = payload.get("action")
            if action != "created":
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            return f"[{repo}] 💬 @{actor} {action} комментарий в Issue/PR #{issue_num}"

        elif event_type == "ReleaseEvent":
            action = payload.get("action")
            tag = payload.get("release", {}).get("tag_name", "?")
            return f"[{repo}] 🚀 @{actor} {action} релиз {tag}"

        elif event_type == "ForkEvent":
            return f"[{repo}] 🍴 @{actor} сделал форк репозитория."

        return None

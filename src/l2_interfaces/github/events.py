"""
Фоновый поллер GitHub.

Мониторит уведомления (Mentions/Reviews) и активность в отслеживаемых репозиториях (Watchers).
Использует внутренний кэш ID событий для обхода проблемы 'GitHub Eventual Consistency'
(задержки появления логов в API).
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict

from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.event.registry import Events
from src.utils.dtime import format_datetime

from src.l0_state.interfaces.github_state import GithubState
from src.l2_interfaces.github.client import GithubClient


class GithubEvents:
    """
    Фоновый мониторинг GitHub (Уведомления аккаунта + Watchers).
    """

    def __init__(
        self,
        client: GithubClient,
        state: GithubState,
        event_bus: EventBus,
        data_dir: Path,
        timezone: int = 0,
    ) -> None:
        """
        Инициализирует поллер.

        Args:
            client: Экземпляр GithubClient.
            state: Объект состояния интерфейса.
            event_bus: Глобальная шина событий.
            data_dir: Путь к хранилищу локальных данных (для персистентности Watchers).
            timezone: Смещение часового пояса.
        """
        self.client = client
        self.state = state
        self.bus = event_bus
        self.data_dir = data_dir
        self.timezone = timezone

        self._is_running = False
        self._polling_task: Optional[asyncio.Task] = None

        self._persistence_file = self.data_dir / "interfaces" / "github" / "tracked_repos.json"
        self._persistence_file.parent.mkdir(parents=True, exist_ok=True)

        # Кэш просмотренных событий для обхода проблемы GitHub Eventual Consistency
        self._seen_event_ids: Dict[str, bool] = {}
        self._initialized_repos: set[str] = set()

    async def start(self) -> None:
        """Запускает фоновый цикл проверки обновлений."""
        if self._is_running:
            return

        self._load_persisted_repos()
        self._is_running = True
        self._polling_task = asyncio.create_task(self._loop())
        system_logger.info("[Github] Фоновый поллинг запущен.")

    async def stop(self) -> None:
        """Останавливает цикл проверки."""
        self._is_running = False
        if self._polling_task:
            self._polling_task.cancel()
            self._polling_task = None
        system_logger.info("[Github] Фоновый поллинг остановлен.")

    # ==========================================================
    # PERSISTENCE (Сохранение на диск)
    # ==========================================================

    def _load_persisted_repos(self) -> None:
        """Загружает список отслеживаемых репозиториев из JSON."""
        if not self._persistence_file.exists():
            return
        try:
            with open(self._persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    self.state.tracked_repos = data
        except Exception as e:
            system_logger.warning(f"[Github] Ошибка чтения tracked_repos.json: {e}")

    def save_persisted_repos(self) -> None:
        """Сохраняет текущий список отслеживаемых репозиториев (с ватермарками)."""
        try:
            with open(self._persistence_file, "w", encoding="utf-8") as f:
                json.dump(self.state.tracked_repos, f, indent=4)
        except Exception as e:
            system_logger.error(f"[Github] Ошибка сохранения tracked_repos.json: {e}")

    def _format_gh_time(self, iso_str: str) -> str:
        """Форматирует ISO строку времени от GitHub в читаемый вид."""
        if not iso_str:
            return ""
        try:
            dt = datetime.strptime(iso_str.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S%z")
            return f"[{format_datetime(dt, self.timezone, '%m-%d %H:%M')}] "
        except Exception:
            return ""

    # ==========================================================
    # POLLING LOOP
    # ==========================================================

    async def _loop(self) -> None:
        """Главный цикл опроса GitHub API."""
        while self._is_running:
            try:
                if self.client.config.agent_account and self.client.token:
                    await self._poll_account_state()

                if self.state.tracked_repos:
                    await self._poll_watched_repos()

            except asyncio.CancelledError:
                break
            except Exception as e:
                system_logger.debug(f"[Github] Ошибка в цикле мониторинга: {e}")

            await asyncio.sleep(self.client.config.polling_interval_sec)

    async def _poll_account_state(self) -> None:
        """Обновляет состояние профиля агента и проверяет непрочитанные уведомления."""
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
                        time_prefix = self._format_gh_time(n.get("updated_at", ""))
                        notif_lines.append(
                            f"- {time_prefix}[in repo: {repo}] {n_type}: {title}"
                        )
                    self.state.unread_notifications = "\n".join(notif_lines)

        except Exception as e:
            system_logger.debug(f"[Github] Ошибка фонового обновления профиля: {e}")

    async def _poll_watched_repos(self) -> None:
        """Мониторит список отслеживаемых репозиториев и генерирует системные события."""
        modified = False

        for repo_name, last_event_id in list(self.state.tracked_repos.items()):
            try:
                events_data = await self.client.request(
                    "GET", f"/repos/{repo_name}/events", params={"per_page": 30}
                )

                if not isinstance(events_data, list) or not events_data:
                    continue

                events_data.reverse()  # Идем от старых к новым

                is_first_poll = repo_name not in self._initialized_repos
                self._initialized_repos.add(repo_name)

                highest_parsed_id = last_event_id

                for event in events_data:
                    event_id = str(event.get("id"))
                    if not event_id or event_id in self._seen_event_ids:
                        continue

                    # Отмечаем как просмотренное
                    self._seen_event_ids[event_id] = True

                    # Защита от утечки памяти
                    if len(self._seen_event_ids) > 1000:
                        for k in list(self._seen_event_ids.keys())[:500]:
                            del self._seen_event_ids[k]

                    parsed_msg = self._parse_github_event(event)

                    if not parsed_msg:
                        continue

                    # Определяем, нужно ли триггерить систему
                    is_new = False
                    if not last_event_id:
                        # Только начали отслеживать репозиторий - заполняем тихо
                        is_new = False

                    elif is_first_poll:
                        # Рестарт агента. Публикуем только те, что объективно больше последнего сохраненного ID
                        try:
                            is_new = int(event_id) > int(last_event_id)
                        except (ValueError, TypeError):
                            is_new = event_id > str(last_event_id)

                    else:
                        # Рантайм. Раз мы его еще не видели (прошли проверку seen_event_ids) - значит оно новое.
                        # Это решает проблему GitHub Eventual Consistency (когда PushEvent приходит с задержкой)
                        is_new = True

                    self.state.add_watcher_event(parsed_msg)

                    if is_new:
                        await self.bus.publish(
                            Events.GITHUB_REPO_ACTIVITY, repo=repo_name, message=parsed_msg
                        )

                    # Обновляем ватермарку ID для сохранения на диск
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
        """Парсит сырое событие GitHub в человекочитаемую строку."""
        event_type = event.get("type")
        actor = event.get("actor", {}).get("login", "Unknown")
        repo = event.get("repo", {}).get("name", "Unknown")
        payload = event.get("payload", {})
        time_prefix = self._format_gh_time(event.get("created_at", ""))

        if event_type == "PushEvent":
            commits = payload.get("commits", [])
            count = payload.get("size", len(commits))
            branch = payload.get("ref", "").replace("refs/heads/", "")

            if count == 0:
                return None

            msg = commits[0].get("message", "").split("\n")[0] if commits else "Без описания"
            branch_str = f" в ветку {branch}" if branch else ""
            return f"{time_prefix}[in repo: {repo}] @{actor} запушил {count} коммит(ов){branch_str}. Последний: '{msg}'"

        elif event_type == "IssuesEvent":
            action = payload.get("action")
            if action not in ("opened", "closed", "reopened", "commented"):
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            title = payload.get("issue", {}).get("title", "")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} issue #{issue_num}: '{title}'"

        elif event_type == "PullRequestEvent":
            action = payload.get("action")
            pr_obj = payload.get("pull_request", {})
            pr_num = pr_obj.get("number", "?")
            title = pr_obj.get("title", "").strip()

            if action == "closed":
                action = "merged" if pr_obj.get("merged") else "closed (without merge)"

            title_str = f": '{title}'" if title else ""
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} Pull Request #{pr_num}{title_str}"

        elif event_type == "IssueCommentEvent":
            action = payload.get("action")
            if action != "created":
                return None
            issue_num = payload.get("issue", {}).get("number", "?")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} комментарий в Issue/PR #{issue_num}"

        elif event_type == "ReleaseEvent":
            action = payload.get("action")
            tag = payload.get("release", {}).get("tag_name", "?")
            return f"{time_prefix}[in repo: {repo}] @{actor} {action} релиз {tag}"

        return None

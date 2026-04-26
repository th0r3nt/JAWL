import asyncio
from pathlib import Path

from src.l2_interfaces.github.client import GithubClient
from src.l3_agent.skills.registry import SkillResult, skill
from src.utils.logger import system_logger
from src.utils._tools import truncate_text, validate_sandbox_path


class GithubLocalGit:
    """Навыки для локальной работы с Git (Клонирование, Коммиты, Пуши) внутри песочницы."""

    def __init__(self, github_client: GithubClient):
        self.github = github_client

    def _mask_token(self, text: str) -> str:
        """
        Скрывает токен из логов и вывода консоли.
        """

        if self.github.token:
            return text.replace(self.github.token, "***")
        return text

    async def _run_git_command(self, cwd: Path, *args: str) -> tuple[int, str, str]:
        """
        Безопасный запуск git команд в подпроцессе.
        """

        try:
            process = await asyncio.create_subprocess_exec(
                "git",
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            return (
                process.returncode,
                self._mask_token(stdout.decode("utf-8", errors="replace").strip()),
                self._mask_token(stderr.decode("utf-8", errors="replace").strip()),
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                "Утилита 'git' не найдена в системе хоста. Установите git."
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise TimeoutError("Таймаут выполнения команды git (> 60 сек).")

    @skill()
    async def git_clone_repository(
        self, owner: str, repo: str, dest_folder: str
    ) -> SkillResult:
        """
        Клонирует Git-репозиторий в песочницу (sandbox/).
        Сохраняет .git директорию для коммитов.
        """

        try:
            if "/" not in dest_folder and "\\" not in dest_folder:
                dest_folder = f"download/{dest_folder}"

            # Используем независимый гейткипер из утилит
            safe_path = validate_sandbox_path(dest_folder)

            if safe_path.exists() and any(safe_path.iterdir()):
                return SkillResult.fail(
                    f"Ошибка: Директория '{safe_path.name}' уже существует и не пуста."
                )

            safe_path.parent.mkdir(parents=True, exist_ok=True)

            if self.github.token:
                repo_url = (
                    f"https://x-access-token:{self.github.token}@github.com/{owner}/{repo}.git"
                )
            else:
                repo_url = f"https://github.com/{owner}/{repo}.git"

            code, out, err = await self._run_git_command(
                safe_path.parent, "clone", repo_url, safe_path.name
            )

            if code != 0:
                return SkillResult.fail(f"Ошибка git clone:\n{err or out}")

            await self._run_git_command(safe_path, "config", "user.name", "JAWL Agent")
            await self._run_git_command(safe_path, "config", "user.email", "agent@jawl.local")

            self.github.state.add_history(f"git_clone: {owner}/{repo}")
            system_logger.info(
                f"[Github] Склонирован репозиторий {owner}/{repo} в {safe_path.name}"
            )

            return SkillResult.ok(
                f"Репозиторий успешно склонирован в sandbox/{safe_path.name}"
            )

        except FileNotFoundError as e:
            return SkillResult.fail(str(e))
        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка при клонировании: {e}")

    @skill()
    async def git_checkout_branch(
        self, repo_folder: str, branch_name: str, create_new: bool = False
    ) -> SkillResult:
        """
        Переключает локальный репозиторий на другую ветку.
        Если create_new=True, создаст новую ветку от текущей.
        """

        try:
            safe_path = validate_sandbox_path(repo_folder)
            if not (safe_path / ".git").exists():
                return SkillResult.fail(
                    "Ошибка: Указанная папка не является git-репозиторием."
                )

            args = ["checkout", "-b", branch_name] if create_new else ["checkout", branch_name]
            code, out, err = await self._run_git_command(safe_path, *args)

            if code != 0:
                return SkillResult.fail(f"Ошибка git checkout:\n{err or out}")

            return SkillResult.ok(f"Успешное переключение на ветку '{branch_name}'.\n{out}")

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка git checkout: {e}")

    @skill()
    async def git_commit_and_push(
        self, repo_folder: str, commit_message: str, branch_name: str
    ) -> SkillResult:
        """
        Индексирует все изменения, создает коммит и пушит в origin.
        """

        if not self.github.token:
            return SkillResult.fail(
                "Ошибка: Для выполнения 'git push' необходим GITHUB_TOKEN."
            )

        try:
            safe_path = validate_sandbox_path(repo_folder)
            if not (safe_path / ".git").exists():
                return SkillResult.fail(
                    "Ошибка: Указанная папка не является git-репозиторием."
                )

            code, out, err = await self._run_git_command(safe_path, "add", ".")
            if code != 0:
                return SkillResult.fail(f"Ошибка git add:\n{err or out}")

            code, status_out, _ = await self._run_git_command(
                safe_path, "status", "--porcelain"
            )
            if not status_out.strip():
                return SkillResult.ok("Нет изменений для коммита. Рабочее дерево чистое.")

            code, out, err = await self._run_git_command(
                safe_path, "commit", "-m", commit_message
            )
            if code != 0:
                return SkillResult.fail(f"Ошибка git commit:\n{err or out}")

            code, push_out, push_err = await self._run_git_command(
                safe_path, "push", "-u", "origin", branch_name
            )
            if code != 0:
                return SkillResult.fail(f"Ошибка git push:\n{push_err or push_out}")

            system_logger.info(
                f"[Github] Сделан коммит и пуш в ветку {branch_name} (Папка: {safe_path.name})"
            )

            report = truncate_text(push_err or push_out, 500)
            return SkillResult.ok(
                f"Изменения успешно зафиксированы и отправлены в origin/{branch_name}.\n{report}"
            )

        except PermissionError as e:
            return SkillResult.fail(str(e))
        except Exception as e:
            return SkillResult.fail(f"Ошибка git commit/push: {e}")

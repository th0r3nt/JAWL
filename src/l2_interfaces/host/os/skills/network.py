import asyncio
import platform
import socket
import urllib.parse
import urllib.request
import urllib.error
import psutil

from src.utils.logger import system_logger
from src.utils._tools import truncate_text

from src.l2_interfaces.host.os.client import HostOSClient

from src.l3_agent.skills.registry import SkillResult, skill
from typing import Optional


_ALLOWED_URL_SCHEMES = ("http", "https")


def _ensure_http_scheme(url: str) -> Optional[str]:
    """Возвращает текст ошибки, если схема URL не http/https. Иначе None."""
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in _ALLOWED_URL_SCHEMES:
        return (
            f"Запрещённая схема URL: '{scheme or '<пусто>'}'. "
            "Разрешены только http:// и https://."
        )
    return None


class HostOSNetwork:
    """
    Навыки агента для сетевой диагностики и взаимодействия.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill()
    async def ping_host(self, host: str, count: int = 4) -> SkillResult:
        """Проверяет доступность узла через ICMP Ping (кроссплатформенно)."""

        # Защита от shell-инъекций: убираем спецсимволы
        clean_host = "".join(c for c in host if c.isalnum() or c in ".-_")

        param = "-n" if platform.system().lower() == "windows" else "-c"

        try:
            # Используем exec (а не shell) для безопасности
            process = await asyncio.create_subprocess_exec(
                "ping",
                param,
                str(count),
                clean_host,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15)
            exit_code = process.returncode

            output = stdout.decode("utf-8", errors="replace").strip()

            system_logger.info(f"[Host OS] Пинг узла {clean_host} (Код: {exit_code})")

            if exit_code == 0:
                return SkillResult.ok(f"Узел {clean_host} доступен.\nВывод:\n{output}")

            else:
                return SkillResult.fail(
                    f"Узел {clean_host} недоступен (Код: {exit_code}).\nВывод:\n{output}"
                )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return SkillResult.fail(
                f"Таймаут: пинг к {clean_host} занял слишком много времени."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка выполнения ping: {e}")

    @skill()
    async def check_port(self, host: str, port: int, timeout: int = 3) -> SkillResult:
        """Проверяет доступность TCP-порта."""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, int(port)), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()

            system_logger.info(f"[Host OS] Проверен порт {host}:{port} (Открыт)")
            return SkillResult.ok(
                f"Порт {port} на хосте {host} открыт и принимает соединения."
            )

        except asyncio.TimeoutError:
            return SkillResult.fail(
                f"Таймаут: порт {port} на {host} не ответил за {timeout} сек."
            )

        except ConnectionRefusedError:
            return SkillResult.fail(f"В соединении отказано: порт {port} на {host} закрыт.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при проверке порта {host}:{port}: {e}")

    @skill()
    async def http_request(
        self, url: str, method: str = "GET", headers: Optional[dict] = None
    ) -> SkillResult:
        """
        Отправляет HTTP-запрос и возвращает ответ.
        """

        limit = self.host_os.config.http_response_max_chars

        scheme_error = _ensure_http_scheme(url)
        if scheme_error:
            return SkillResult.fail(scheme_error)

        def _make_request():
            req_headers = headers or {"User-Agent": "JAWL-Agent/1.0"}
            req = urllib.request.Request(url, method=method.upper(), headers=req_headers)

            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status = response.status
                    body = response.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                status = e.code
                body = e.read().decode("utf-8", errors="replace")

            # Обрезаем вывод для защиты контекста
            body = truncate_text(body, limit)
            return status, body

        try:
            status_code, content = await asyncio.to_thread(_make_request)
            system_logger.info(
                f"[Host OS] HTTP {method.upper()} запрос к {url} (Статус: {status_code})"
            )

            return SkillResult.ok(f"Статус: {status_code}\n\nТело ответа:\n{content}")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при HTTP-запросе: {e}")

    @skill()
    async def list_active_connections(self, state: str = "LISTEN") -> SkillResult:
        """Показывает активные сетевые соединения на хосте."""

        try:
            connections = psutil.net_connections(kind="inet")
            filtered = [conn for conn in connections if conn.status == state.upper()]

            if not filtered:
                return SkillResult.ok(f"Нет соединений в состоянии '{state}'.")

            lines = [f"Сетевые соединения (состояние: {state.upper()}):"]
            for conn in filtered:
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}"
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "*:*"
                pid_info = f" (PID: {conn.pid})" if conn.pid else ""
                lines.append(f"- Локальный: {laddr} | Удаленный: {raddr}{pid_info}")

            system_logger.info(f"[Host OS] Запрошены активные соединения ({state})")
            return SkillResult.ok("\n".join(lines))

        except psutil.AccessDenied:
            return SkillResult.fail(
                "Отказано в доступе (требуются права администратора для чтения всех соединений)."
            )

        except Exception as e:
            return SkillResult.fail(f"Ошибка при получении соединений: {e}")

    @skill()
    async def resolve_dns(self, domain: str) -> SkillResult:
        """Возвращает IP-адреса, привязанные к домену."""

        try:
            # socket.gethostbyname_ex возвращает: (hostname, aliaslist, ipaddrlist)
            _, aliases, ips = await asyncio.to_thread(socket.gethostbyname_ex, domain)

            system_logger.info(f"[Host OS] DNS запрос для {domain}")

            report = f"DNS записи для '{domain}':\n- IP адреса: {', '.join(ips)}"
            if aliases:
                report += f"\n- Алиасы: {', '.join(aliases)}"

            return SkillResult.ok(report)

        except socket.gaierror:
            return SkillResult.fail(f"Ошибка: Не удалось разрешить домен '{domain}'.")

        except Exception as e:
            return SkillResult.fail(f"Ошибка при DNS-запросе: {e}")

    @skill()
    async def download_file(self, url: str, dest_filename: str) -> SkillResult:
        """Скачивает файл из сети на диск. По умолчанию сохраняет в sandbox/download/."""

        try:
            scheme_error = _ensure_http_scheme(url)
            if scheme_error:
                return SkillResult.fail(scheme_error)

            # Если агент передал просто имя файла, кидаем его в папку загрузок
            if "/" not in dest_filename and "\\" not in dest_filename:
                dest_filename = f"download/{dest_filename}"

            # Гейткипер проверит права на запись в этот путь
            safe_path = self.host_os.validate_path(dest_filename, is_write=True)

            def _download():
                req = urllib.request.Request(url, headers={"User-Agent": "JAWL-Agent/1.0"})
                with urllib.request.urlopen(req, timeout=30) as response, open(
                    safe_path, "wb"
                ) as out_file:
                    out_file.write(response.read())

            await asyncio.to_thread(_download)

            system_logger.info(f"[Host OS] Файл {safe_path.name} скачан из {url}")
            return SkillResult.ok(f"Файл успешно скачан и сохранен по пути: {safe_path.name}")

        except PermissionError as e:
            return SkillResult.fail(str(e))

        except Exception as e:
            return SkillResult.fail(f"Ошибка при скачивании файла: {e}")

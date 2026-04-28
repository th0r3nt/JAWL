import asyncio
import platform
import socket
import psutil

from src.utils.logger import system_logger

from src.l2_interfaces.host.os.client import HostOSClient

from src.l3_agent.skills.registry import SkillResult, skill


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
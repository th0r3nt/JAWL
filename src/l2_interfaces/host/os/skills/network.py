"""
Network diagnostics skills (ICMP, TCP).
Used by the main agent and subagents (SYSADMIN) to verify host availability and monitor sockets.
"""

import asyncio
import platform
import socket
import psutil

from src.utils.logger import main_logger

from src.l2_interfaces.host.os.client import HostOSClient, HostOSAccessLevel
from src.l2_interfaces.host.os.decorators import require_access

from src.l3_agent.skills.registry import SkillResult, skill
from src.l3_agent.swarm.roles import Subagents


class HostOSNetwork:
    """
    Agent skills for network diagnostics and interaction.
    """

    def __init__(self, host_os_client: HostOSClient):
        self.host_os = host_os_client

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def ping_host(self, host: str, count: int = 4) -> SkillResult:
        """
        Checks host availability via ICMP Ping.
        """

        clean_host = "".join(c for c in host if c.isalnum() or c in ".-_")

        param = "-n" if platform.system().lower() == "windows" else "-c"

        try:
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

            main_logger.info(f"[Host OS] Ping to host {clean_host} (Code: {exit_code})")

            if exit_code == 0:
                return SkillResult.ok(f"Host {clean_host} is reachable.\nOutput:\n{output}")

            else:
                return SkillResult.fail(
                    f"Host {clean_host} is unreachable (Code: {exit_code}).\nOutput:\n{output}"
                )

        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            return SkillResult.fail(f"Timeout: ping to {clean_host} took too long.")

        except Exception as e:
            return SkillResult.fail(f"Error executing ping: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def check_port(self, host: str, port: int, timeout: int = 3) -> SkillResult:
        """
        Checks TCP port availability.
        """

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, int(port)), timeout=timeout
            )
            writer.close()
            await writer.wait_closed()

            main_logger.info(f"[Host OS] Checked port {host}:{port} (Open)")
            return SkillResult.ok(f"Port {port} on host {host} is open.")

        except asyncio.TimeoutError:
            return SkillResult.fail(
                f"Timeout: port {port} on {host} did not respond within {timeout} sec."
            )

        except ConnectionRefusedError:
            return SkillResult.fail(f"Connection refused: port {port} on {host} is closed.")

        except Exception as e:
            return SkillResult.fail(f"Error checking port {host}:{port}: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def list_active_connections(self, state: str = "LISTEN") -> SkillResult:
        """
        Lists host's active network connections.
        """

        try:
            connections = psutil.net_connections(kind="inet")
            filtered = [conn for conn in connections if conn.status == state.upper()]

            if not filtered:
                return SkillResult.ok(f"No connections in state '{state}'.")

            lines = [f"Network connections (state: {state.upper()}):"]
            for conn in filtered:
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}"
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "*:*"
                pid_info = f" (PID: {conn.pid})" if conn.pid else ""
                lines.append(f"- Local: {laddr} | Remote: {raddr}{pid_info}")

            main_logger.info(f"[Host OS] Requested active connections ({state})")
            return SkillResult.ok("\n".join(lines))

        except psutil.AccessDenied:
            return SkillResult.fail(
                "Access denied (administrator privileges are required to read all connections)."
            )

        except Exception as e:
            return SkillResult.fail(f"Error getting connections: {e}")

    @skill(swarm=[Subagents.SYSADMIN])
    @require_access(HostOSAccessLevel.OBSERVER)
    async def resolve_dns(self, domain: str) -> SkillResult:
        """
        Returns IP addresses bound to domain.
        """

        try:
            _, aliases, ips = await asyncio.to_thread(socket.gethostbyname_ex, domain)

            main_logger.info(f"[Host OS] DNS query for {domain}")

            report = f"DNS records for '{domain}':\n- IP addresses: {', '.join(ips)}"
            if aliases:
                report += f"\n- Aliases: {', '.join(aliases)}"

            return SkillResult.ok(report)

        except socket.gaierror:
            return SkillResult.fail(f"Error: Failed to resolve domain '{domain}'.")

        except Exception as e:
            return SkillResult.fail(f"Error during DNS query: {e}")

"""
JAWL System Orchestrator.

Manages startup, operational loops, and graceful shutdown of the SystemContainer.
"""

import asyncio

from src.utils.logger import main_logger
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events
from src.utils._tools import update_last_active_time

from src.system.container import SystemContainer


class SystemOrchestrator:
    """
    Subsystem startup and shutdown lifecycles orchestrator.
    """

    def __init__(self, container: SystemContainer) -> None:
        self.container = container

    async def run(self) -> int:
        """
        Starts the system lifecycle.
        """

        # Setup event routing
        EventBridge(self.container).setup_routing()

        # Start L2 components
        started_components = []
        for component in self.container.lifecycle_components:
            try:
                await component.start()
                started_components.append(component)
            except Exception as e:
                main_logger.error(
                    f"[System] Failed to start {component.__class__.__name__}: {e}"
                )
        self.container.lifecycle_components = started_components

        agent_name = self.container.settings.identity.agent_name
        main_logger.info(f"[System] JAWL started successfully. Agent name: {agent_name}")

        await self.container.event_bus.publish(Events.SYSTEM_CORE_START, status="online")

        # Background stop signal file watcher
        stop_watcher_task = asyncio.create_task(self._watch_for_stop_file())

        # Main heartbeat loop execution
        await self.container.heartbeat.start()

        # Heartbeat concluded
        stop_watcher_task.cancel()
        return self.container.exit_code

    async def stop(self) -> None:
        """
        Graceful stopping and resource cleanup.
        """
        
        main_logger.info("[System] Initiating JAWL shutdown.")

        # Обновляем маркер активности перед остановкой, фиксируя точное время выключения
        update_last_active_time()

        await self.container.event_bus.publish(Events.SYSTEM_CORE_STOP, status="offline")

        if self.container.heartbeat:
            self.container.heartbeat.stop()

        for component in reversed(self.container.lifecycle_components):
            try:
                await component.stop()
            except Exception as e:
                main_logger.error(
                    f"[System] Error stopping {component.__class__.__name__}: {e}"
                )

        if self.container.vector:
            await self.container.vector.disconnect()
        if self.container.sql:
            await self.container.sql.disconnect()
        if self.container.graph:
            await self.container.graph.disconnect()

        if self.container.event_bus:
            await self.container.event_bus.stop()

        if self.container.llm_client:
            await self.container.llm_client.close()

        sub_llm = self.container.sub_llm_client
        if sub_llm and sub_llm is not self.container.llm_client:
            await sub_llm.close()

        main_logger.info("[System] Shutdown complete.")

    async def _watch_for_stop_file(self) -> None:
        """
        Background poller: awaits agent.stop file from CLI for graceful stop.
        """

        stop_file = self.container.local_data_dir / "agent.stop"

        if stop_file.exists():
            try:
                stop_file.unlink()
            except Exception:
                pass

        try:
            while True:
                if stop_file.exists():
                    main_logger.info(
                        "[System] Received stop file signal (agent.stop). Initiating graceful shutdown."
                    )
                    try:
                        stop_file.unlink()
                    except Exception:
                        pass

                    await self.container.event_bus.publish(
                        Events.SYSTEM_SHUTDOWN_REQUESTED,
                        reason="Stopped by user via CLI",
                    )
                    break
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

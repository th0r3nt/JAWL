"""
System Event Router Bridge.

De-couples subscription routing from the main loader. Listens to EventBus
events and proxies wakeups to Heartbeat, while processing system lifecycle commands
and runtime config changes.
"""

from typing import TYPE_CHECKING, Any, Callable, Coroutine

from src.utils.logger import main_logger
from src.utils.event.registry import Events, EventConfig

if TYPE_CHECKING:
    from src.system.container import SystemContainer


class EventBridge:
    """Event router and bridge (Event-Driven pattern)."""

    def __init__(self, container: "SystemContainer"):
        self.container = container

    def setup_routing(self) -> None:
        """Subscribes Heartbeat and system handlers to EventBus events."""

        # Specific system subscriptions
        self.container.event_bus.subscribe(
            Events.SYSTEM_SHUTDOWN_REQUESTED, self._handle_shutdown
        )
        self.container.event_bus.subscribe(Events.SYSTEM_REBOOT_REQUESTED, self._handle_reboot)
        self.container.event_bus.subscribe(
            Events.SYSTEM_CONFIG_UPDATED, self._handle_config_update
        )
        self.container.event_bus.subscribe(
            Events.SYSTEM_DASHBOARD_UPDATE, self._handle_dashboard_update
        )
        self.container.event_bus.subscribe(
            Events.SYSTEM_SLEEP_REQUESTED, self._handle_sleep_requested
        )

        # Dynamic Heartbeat subscription mapping
        system_events = {
            Events.SYSTEM_CORE_STOP.name,
            Events.SYSTEM_SHUTDOWN_REQUESTED.name,
            Events.SYSTEM_REBOOT_REQUESTED.name,
        }

        for event in Events.all():
            if event.name in system_events:
                continue

            # Closure to lock event reference inside loop generator
            handler = self._create_heartbeat_handler(event)
            self.container.event_bus.subscribe(event, handler)

    def _create_heartbeat_handler(
        self, evt: EventConfig
    ) -> Callable[..., Coroutine[Any, Any, None]]:
        """
        Generates async callback proxying event parameters to Heartbeat.
        """

        async def handler(**kwargs: Any) -> None:
            if evt == Events.SYSTEM_CORE_STOP:
                return

            if self.container.heartbeat:
                self.container.heartbeat.answer_to_event(
                    level=evt.level,
                    event_name=evt.name,
                    payload=kwargs,
                    requires_attention=evt.requires_attention,
                )

        return handler

    async def _handle_sleep_requested(self, **kwargs: Any) -> None:
        """
        Custom sleep mode request handler.
        """
        duration = kwargs.get("duration", 1800)
        depth = kwargs.get("depth", "deep")
        if self.container.heartbeat:
            self.container.heartbeat.set_custom_sleep(duration, depth)

    # =========================================================================
    # SYSTEM COMMANDS AND CONFIGURATION CONTROLLERS
    # =========================================================================

    async def _handle_config_update(self, **kwargs: Any) -> None:
        """
        Runtime configuration update handler (Hot Reload).
        """

        key = kwargs.get("key")

        # Heartbeat settings
        if key in ("heartbeat_interval", "continuous_cycle"):
            if self.container.heartbeat:
                self.container.heartbeat.update_config(key, kwargs.get("value"))

        # Relational SQL limits
        elif key == "db_limit":
            module = kwargs.get("module", "")
            val = kwargs.get("value", 0)

            if self.container.sql:
                self.container.sql.update_limits(module, val)
                main_logger.info(f"[System] Runtime configuration updated for {module}: {val}")

        # Episodic context depth (Ticks)
        elif key == "context_depth":
            high = kwargs.get("high_ticks", 0)
            medium = kwargs.get("medium_ticks", 0)
            low = kwargs.get("low_ticks", 0)

            if self.container.sql:
                self.container.sql.update_context_depth(high, medium, low)

            total = high + medium + low
            main_logger.info(f"[System] Runtime context depth updated: {total} ticks")

    async def _handle_dashboard_update(self, **kwargs: Any) -> None:
        """
        Updates or removes custom Markdown block in L0 State.
        """

        name = kwargs.get("name")
        content = kwargs.get("content")

        if name and self.container.dashboard_state:
            self.container.dashboard_state.update_block(name, content)

    async def _handle_shutdown(self, **kwargs: Any) -> None:
        """
        Handles system shutdown signal.
        """

        self.container.exit_code = 0
        if self.container.heartbeat:
            self.container.heartbeat.stop()

    async def _handle_reboot(self, **kwargs: Any) -> None:
        """
        Handles system reboot signal.
        """

        self.container.exit_code = 1
        if self.container.heartbeat:
            self.container.heartbeat.stop()

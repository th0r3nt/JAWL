"""
Оркестратор системы JAWL.
Управляет жизненным циклом (запуск, работа, остановка) собранного контейнера.
"""

import asyncio

from src.utils.logger import main_logger
from src.utils.event.bridge import EventBridge
from src.utils.event.registry import Events
from src.system.container import SystemContainer


class SystemOrchestrator:
    """
    Управляющий запуском, работой и остановкой подсистем.
    """

    def __init__(self, container: SystemContainer) -> None:
        self.container = container

    async def run(self) -> int:
        """
        Запускает жизненный цикл системы.
        """

        # Настройка маршрутизации событий
        EventBridge(self.container).setup_routing()  # Надо бы эту штуку через DI передавать?

        # Запуск компонентов L2
        started_components = []
        for component in self.container.lifecycle_components:
            try:
                await component.start()
                started_components.append(component)
            except Exception as e:
                main_logger.error(
                    f"[System] Ошибка запуска {component.__class__.__name__}: {e}"
                )
        self.container.lifecycle_components = started_components

        agent_name = self.container.settings.identity.agent_name
        main_logger.info(f"[System] JAWL успешно запущен. Имя агента: {agent_name}")

        await self.container.event_bus.publish(Events.SYSTEM_CORE_START, status="online")

        # Фоновый слушатель остановки из CLI
        stop_watcher_task = asyncio.create_task(self._watch_for_stop_file())

        # Точка входа в бесконечный цикл (Сердцебиение агента)
        await self.container.heartbeat.start()

        # Если мы дошли сюда - агент остановился штатно
        stop_watcher_task.cancel()
        return self.container.exit_code

    async def stop(self) -> None:
        """
        Плавная остановка и очистка ресурсов.
        """

        main_logger.info("[System] Инициирована остановка JAWL. Нанимаем киллеров.")
        await self.container.event_bus.publish(Events.SYSTEM_CORE_STOP, status="offline")

        if self.container.heartbeat:
            self.container.heartbeat.stop()

        for component in reversed(self.container.lifecycle_components):
            try:
                await component.stop()
            except Exception as e:
                main_logger.error(
                    f"[System] Ошибка при остановке {component.__class__.__name__}: {e}"
                )

        # Безопасное отключение баз данных
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

        # Закрываем сессии субагентов, только если это отдельный клиент
        sub_llm = self.container.sub_llm_client
        if sub_llm and sub_llm is not self.container.llm_client:
            await sub_llm.close()

        main_logger.info("[System] Остановка завершена. Процесс выслежен и убит.")

    async def _watch_for_stop_file(self) -> None:
        """
        Фоновая задача: ждет появления файла agent.stop от CLI для плавной остановки.
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
                        "[System] Получен сигнал от CLI (agent.stop). Запуск плавной остановки."
                    )
                    try:
                        stop_file.unlink()
                    except Exception:
                        pass

                    await self.container.event_bus.publish(
                        Events.SYSTEM_SHUTDOWN_REQUESTED,
                        reason="Остановка пользователем из меню",
                    )
                    break
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            pass

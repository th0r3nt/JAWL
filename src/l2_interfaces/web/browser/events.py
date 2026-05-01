"""
Фоновый Watchdog браузера.

Следит за временем простоя (Idle Time). Если агент открыл браузер и забыл его закрыть,
Watchdog автоматически прибьет процесс Chromium для освобождения оперативной памяти.
"""

import asyncio
import time
from typing import Optional
from src.utils.logger import system_logger
from src.l2_interfaces.web.browser.client import WebBrowserClient


class WebBrowserEvents:
    """
    Watchdog оперативной памяти. Закрывает браузер при долгом простое.
    """

    def __init__(self, client: WebBrowserClient) -> None:
        self.client = client
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Запускает Watchdog."""
        if self._is_running:
            return
        self._is_running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        """Останавливает Watchdog."""
        self._is_running = False
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        """Цикл проверки простоя браузера."""
        while self._is_running:
            try:
                # Если браузер открыт, проверяем таймер простоя
                if self.client.page and not self.client.page.is_closed():
                    idle_time = time.time() - self.client.last_activity_time

                    if idle_time > self.client.config.idle_timeout_sec:
                        system_logger.info(
                            f"[Web Browser] Браузер не использовался {int(idle_time)} сек. Авто-закрытие для освобождения ОЗУ."
                        )
                        await self.client.close_browser()

            except asyncio.CancelledError:
                break

            except Exception as e:
                system_logger.error(f"[Web Browser] Ошибка в Watchdog: {e}")

            await asyncio.sleep(60)  # Проверяем раз в минуту

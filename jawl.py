"""
Главный скрипт запуска фреймворка JAWL.
Управляет бесконечным циклом перезапуска (watchdog-обертка) для восстановления
агента после критических сбоев или команд на перезагрузку.
"""

import asyncio
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.main import main
from src.utils.logger import system_logger

if __name__ == "__main__":
    try:
        while True:
            # В конце возвращает 0 (если получен сигнал отключения) либо 1 (сигнал перезагрузки)
            exit_code = asyncio.run(main())

            if exit_code == 0:
                break

            system_logger.info("\nПерезагрузка системы.\n")
            time.sleep(3)  # Даем ОС время на освобождение сетевых сокетов и файлов БД

    except KeyboardInterrupt:
        sys.exit(0)

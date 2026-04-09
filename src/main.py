import asyncio
import os

# utils
from src.utils.logger import system_logger

# l0_state

# l1_databases
from src.l1_databases.vector.db import VectorDB

# l2_interfaces

# l3_agent


class System:
    """
    Главный класс.
    Инициализирует все слои.
    Управляет запуском/закрытием системы.
    """

    def __init__(self):
        pass

    # l0_state
    def setup_l0_state(self):
        """
        Инициализирует нулевой слой: состояние.
        """
        pass

    # l1_databases
    def setup_l1_databases(self):
        """
        Инициализирует первый слой: базы данных.
        """
        # 1. Читаем конфиг/путь (например, 'local_data/vector_storage')
        db_path = os.path.join(os.getcwd(), "src", "utils", "local", "data", "vector_storage")
        
        # 2. Инициализируем БД (Инжектим путь)
        self.vector_db = VectorDB(storage_path=db_path)

    # l2_interfaces
    def setup_l2_interfaces(self):
        """
        Инициализирует второй слой: интерфейсы.
        """
        pass

    # l3_agent
    def setup_l3_agent(self):
        """
        Инициализирует третий слой: агента.
        """
        pass

    # ===========================================
    # RUN & STOP
    # ===========================================

    def run(self):
        """
        Инициализирует систему.
        """
        pass

    def stop(self):
        """
        Корректно закрывает подключения к базам данных/интерфейсам
        """
        pass


# ===================================================================
# MAIN
# ===================================================================


async def main(self):
    try:
        system = System()
        system.run()
    except Exception as e:
        system_logger.error(f"Ошибка при работе системы: {e}")
    finally:
        system.stop()


if __name__ == "__main__":
    asyncio.run(main())

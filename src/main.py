import asyncio
from src.utils.logger import system_logger


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
        pass

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

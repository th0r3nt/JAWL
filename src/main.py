import asyncio
from pathlib import Path

# utils
from src.utils.logger import system_logger
from src.utils.event.bus import EventBus
from src.utils.settings import load_config

# l0_state
# :/

# l1_databases
from src.l1_databases.vector.manager import VectorManager
from src.l1_databases.sql.manager import SQLManager

# l2_interfaces

# l3_agent


class System:
    """
    Главный класс.
    Инициализирует все слои.
    Управляет запуском/закрытием системы.
    """

    def __init__(self):
        self.event_bus = EventBus()

        # Загружаем конфиги:
        self.settings, self.interfaces_config = load_config()

        # Базовые директории
        self.root_dir = Path.cwd()
        self.local_data_dir = self.root_dir / "src" / "utils" / "local" / "data"

        # Компоненты системы
        self.vector: VectorManager | None = None
        self.sql: SQLManager | None = None

    async def setup_l0_state(self):
        """Инициализирует нулевой слой: состояние."""
        pass

    # l1_databases
    async def setup_l1_databases(self):
        """
        Инициализирует первый слой: базы данных.
        """

        # SQLDB
        sql_db_path = self.local_data_dir / "agent.db"
        self.sql = SQLManager(db_path=sql_db_path)
        await self.sql.connect()

        # Vector DB
        vector_db_path = self.local_data_dir / "vector_db"
        embedding_model_path = self.local_data_dir / "embeddings"
        self.vector = VectorManager(
            db_path=vector_db_path,  # Путь к базе
            model_path=embedding_model_path,  # Путь к эмбеддинг модели
            embedding_model_name=self.settings.system.vector_db.embedding_model,  # Название модели в конфиге
        )
        await self.vector.connect()

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

    async def run(self):
        """Инициализирует систему."""
        system_logger.info("[System] Запуск JAWL.")

        await self.setup_l0_state()
        await self.setup_l1_databases()
        await self.setup_l2_interfaces()
        await self.setup_l3_agent()

        system_logger.info("[System] Система успешно запущена.")

        # Здесь в будущем будет запуск Heartbeat-цикла
        # await self.heartbeat.loop()

    async def stop(self):
        """Корректно закрывает подключения к базам данных/интерфейсам."""
        system_logger.info("[System] Инициирована остановка JAWL.")

        if self.vector:
            await self.vector.disconnect()

        if self.sql:
            await self.sql.disconnect()

        system_logger.info("[System] Остановка завершена.")


# ===================================================================
# MAIN
# ===================================================================


async def main(self):
    try:
        event_bus = EventBus()

        system = System(event_bus=event_bus)
        system.run()

    except Exception as e:
        system_logger.error(f"Ошибка при работе системы: {e}")

    finally:
        system.stop()


if __name__ == "__main__":
    asyncio.run(main())

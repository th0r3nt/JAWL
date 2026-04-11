import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.l1_databases.sql.tables import Base
from src.utils.logger import system_logger


class SQLDB:
    """
    Асинхронный класс инициализации SQLite.
    Управляет пулом соединений и сессиями.
    """

    def __init__(self, db_path: str):
        # Если это не in-memory база, убеждаемся, что папка существует
        if db_path != ":memory:":
            dir_name = os.path.dirname(db_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

        db_url = f"sqlite+aiosqlite:///{db_path}"

        self.engine = create_async_engine(db_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def connect(self):
        """Создает таблицы, если их нет, и подготавливает БД к работе."""
        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            system_logger.info("[System] SQL база данных успешно инициализирована.")
        except Exception as e:
            system_logger.error(f"[System] Критическая ошибка при запуске SQL базы данных: {e}")
            raise e

    async def disconnect(self):
        """Корректно закрывает соединения при остановке системы."""
        if self.engine:
            await self.engine.dispose()
            system_logger.info("[System] Подключение к SQL базе данных закрыто.")

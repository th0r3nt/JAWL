"""
Модуль инициализации реляционной базы данных (SQLite).

Низкоуровневая обертка для асинхронного взаимодействия с SQLite.
Управляет пулом соединений (SQLAlchemy AsyncEngine) и фабрикой сессий для всего слоя L1.
"""

import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.l1_databases.sql.tables import Base
from src.utils.logger import system_logger


class SQLDB:
    """
    Асинхронный менеджер инициализации SQLite.
    Отвечает за создание таблиц, управление пулом соединений и выдачу сессий.
    """

    def __init__(self, db_path: str) -> None:
        """
        Инициализирует движок базы данных и фабрику сессий.

        Args:
            db_path: Абсолютный или относительный путь к файлу .db, либо ':memory:' для работы в ОЗУ.
        """

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

    async def connect(self) -> None:
        """
        Создает физическое подключение к SQLite и генерирует схему таблиц, если они отсутствуют.
        Должно вызываться строго один раз при старте жизненного цикла системы.

        Raises:
            Exception: В случае нехватки прав доступа к директории или конфликта блокировок.
        """

        try:
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            system_logger.info("[SQL DB] База данных успешно инициализирована.")
        except Exception as e:
            system_logger.error(f"[SQL DB] Критическая ошибка при запуске базы данных: {e}")
            raise e

    async def disconnect(self) -> None:
        """
        Безопасно уничтожает пул соединений (Engine) и сбрасывает незакрытые транзакции.
        Предотвращает утечки дескрипторов (SQLite Database is locked) при перезагрузке системы.
        """

        if self.engine:
            await self.engine.dispose()
            system_logger.info("[SQL DB] Подключение к базе данных закрыто.")

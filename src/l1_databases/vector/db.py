import os
from typing import List
from qdrant_client import AsyncQdrantClient, models

from src.utils.logger import system_logger


class VectorDB:
    """
    Асинхронный класс инициализации векторной базы данных.
    Работает в локальном режиме (без Docker) через Qdrant.
    """

    def __init__(self, db_path: str, collections: List[str], vector_size: int):
        self.db_path = db_path
        self.client: AsyncQdrantClient | None = None
        self.collections = collections
        self.vector_size = vector_size

    async def connect(self):
        """
        Инициализирует подключение и создает файлы базы на диске.
        Вызывается при старте системы.
        """
        try:
            # Убеждаемся, что директория для БД существует
            os.makedirs(self.db_path, exist_ok=True)

            # Поднимаем локальный клиент Qdrant
            self.client = AsyncQdrantClient(path=self.db_path)

            # Создаем коллекции
            for coll in self.collections:
                if not await self.client.collection_exists(coll):
                    await self.client.create_collection(
                        collection_name=coll,
                        vectors_config=models.VectorParams(
                            size=self.vector_size,
                            distance=models.Distance.COSINE, # Используем косинусное расстояние
                        ),
                    )

            system_logger.info(
                f"[Vector DB] База данных успешно инициализирована по пути: {self.db_path}"
            )

        except Exception as e:
            system_logger.error(
                f"[Vector DB] Критическая ошибка при запуске базы данных: {e}"
            )
            raise e

    async def disconnect(self):
        """
        Корректно закрывает базу данных при выключении системы.
        """
        if self.client:
            self.client = None
            system_logger.info("[Vector DB] Подключение к базе данных закрыто.")

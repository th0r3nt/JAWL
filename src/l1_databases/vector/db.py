"""
Клиент векторной базы данных Qdrant.

Обеспечивает создание локальных In-Memory/On-Disk коллекций и защиту от
повреждения данных. В случае изменения размерности вектора в конфигах
система автоматически инициирует удаление старого кэша для предотвращения крашей.
"""

import shutil
from pathlib import Path
from typing import List
from qdrant_client import AsyncQdrantClient, models

from src.utils.logger import system_logger


class VectorDB:
    """Менеджер подключения и структуры векторной базы Qdrant."""

    def __init__(self, db_path: str, collections: List[str], vector_size: int) -> None:
        """
        Инициализирует пути и параметры для подключения к Qdrant.

        Args:
            db_path: Путь к директории хранения файлов базы данных.
            collections: Список имен коллекций, которые должны быть созданы ('knowledge', 'thoughts').
            vector_size: Размерность векторов (должна строго совпадать с используемой embedding-моделью).
        """

        self.db_path = Path(db_path)
        self.client: AsyncQdrantClient | None = None
        self.collections = collections
        self.vector_size = vector_size

    async def connect(self) -> None:
        """
        Устанавливает соединение с локальной БД Qdrant.
        При первом запуске автоматически создает коллекции и Payload Index для тегов.
        Если обнаружено фатальное повреждение кэша базы (например, из-за изменения vector_size) —
        выполняет принудительный Hard Reset (удаляет директорию и создает чистую базу).

        Raises:
            Exception: Если базу невозможно прочитать или пересоздать.
        """
        self.db_path.mkdir(parents=True, exist_ok=True)

        try:
            self.client = AsyncQdrantClient(path=str(self.db_path))

        except Exception as e:
            if "ValidationError" in str(type(e)) or "CreateCollection" in str(e):
                system_logger.warning(
                    "[Vector DB] Обнаружена несовместимость версий или повреждение локальной БД. "
                    "Инициировано автоматическое восстановление."
                )
                shutil.rmtree(self.db_path, ignore_errors=True)
                self.db_path.mkdir(parents=True, exist_ok=True)
                self.client = AsyncQdrantClient(path=str(self.db_path))
            else:
                system_logger.error(
                    f"[Vector DB] Критическая ошибка при запуске базы данных: {e}"
                )
                raise e

        # Проверяем и создаем коллекции, если их нет
        for coll in self.collections:
            if not await self.client.collection_exists(coll):
                await self.client.create_collection(
                    collection_name=coll,
                    vectors_config=models.VectorParams(
                        size=self.vector_size,
                        distance=models.Distance.COSINE,
                    ),
                )
                system_logger.info(f"[Vector DB] Создана коллекция: {coll}")

            # Создаем KEYWORD индекс для тегов (Qdrant игнорирует вызов, если индекс уже существует)
            # Это гарантирует, что поиск по tags_filter будет работать за O(1), а не O(N)
            try:
                await self.client.create_payload_index(
                    collection_name=coll,
                    field_name="tags",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception as idx_err:
                system_logger.debug(
                    f"[Vector DB] Индекс для 'tags' в '{coll}' уже существует или произошла ошибка: {idx_err}"
                )

        system_logger.info(f"[Vector DB] База данных инициализирована по пути: {self.db_path}")

    async def disconnect(self) -> None:
        """Корректно закрывает базу данных при выключении системы."""
        if self.client:
            self.client = None
            system_logger.info("[Vector DB] Подключение к базе данных закрыто.")

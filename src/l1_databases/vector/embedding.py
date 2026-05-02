"""
Векторный синтезатор (Embedding Model Wrapper).

Обертка над библиотекой FastEmbed (ONNX).
Отвечает за генерацию числовых векторов (эмбеддингов) из текста
исключительно локально на CPU хост-машины, что экономит деньги и гарантирует приватность.
"""

import os
import shutil
import asyncio
from fastembed import TextEmbedding

from src.utils.logger import system_logger


class EmbeddingModel:
    """
    Класс для генерации векторных представлений (embeddings).
    Использует FastEmbed (ONNX) для быстрой работы на CPU.
    Имеет встроенный механизм восстановления при повреждении кэша.
    """

    def __init__(
        self, model_path: str, model_name: str = "intfloat/multilingual-e5-small"
    ) -> None:
        """
        Инициализирует и скачивает (при необходимости) ONNX-модель.
        Содержит встроенный Fallback: при повреждении файлов модели автоматически сносит кэш
        и скачивает веса заново.

        Args:
            model_path: Директория для хранения весов модели.
            model_name: Идентификатор модели в репозитории FastEmbed.
        """

        os.makedirs(model_path, exist_ok=True)

        self.model_path = model_path
        self.model_name = model_name

        system_logger.info(
            f"[Vector DB] Инициализация локальной embedding модели: {self.model_name}."
        )

        try:
            # Пытаемся загрузить модель из кэша (или скачать)
            self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_path)

        except Exception as e:
            # Если словили ошибку (например ONNXRuntimeError: NO_SUCHFILE), значит кэш поврежден
            system_logger.warning(
                f"[Vector DB] Обнаружено повреждение файлов модели эмбеддингов ({e}). "
                "Очистка кэша и повторная загрузка."
            )
            # Сносим папку с битым кэшем
            shutil.rmtree(self.model_path, ignore_errors=True)
            os.makedirs(self.model_path, exist_ok=True)

            # Пробуем инициализировать (и скачать) заново
            self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_path)

        system_logger.info(
            f"[Vector DB] Embedding модель готова к работе (путь: {self.model_path})."
        )

    async def get_embedding(self, text: str) -> list[float]:
        """
        Синтезирует эмбеддинг для переданного текста.
        Выполняется в отдельном потоке (asyncio.to_thread), чтобы тяжелые вычисления
        ONNXRuntime не блокировали асинхронный Event Loop ядра агента.

        Args:
            text: Входящий текст для векторизации.

        Returns:
            Сгенерированный тензор чисел (List of floats).

        Raises:
            RuntimeError: Если модель не была успешно загружена.
        """

        if not self.model:
            raise RuntimeError("Ошибка: модель не инициализирована.")

        # FastEmbed возвращает генератор, берем первый элемент и конвертируем в list
        embedding_generator = await asyncio.to_thread(self.model.embed, text)
        embeddings_list = list(embedding_generator)

        return embeddings_list[0].tolist()

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Генерирует эмбеддинги для массива строк одновременно (Batching).
        Используется в механизме GraphRAG для резкого ускорения векторизации
        множественных запросов (нейросети работают с батчами на порядки быстрее).

        Args:
            texts: Список текстов для векторизации.

        Returns:
            Список тензоров (List of lists of floats).

        Raises:
            RuntimeError: Если модель не инициализирована.
        """
        
        if not self.model:
            raise RuntimeError("Ошибка: модель не инициализирована.")

        if not texts:
            return []

        # FastEmbed поддерживает передачу списка строк
        embedding_generator = await asyncio.to_thread(self.model.embed, texts)

        # Конвертируем генератор numpy array в обычный питоновский список списков
        return [emb.tolist() for emb in embedding_generator]

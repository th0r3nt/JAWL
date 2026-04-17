import os
import asyncio
from fastembed import TextEmbedding

from src.utils.logger import system_logger


class EmbeddingModel:
    """
    Класс для генерации векторных представлений (embeddings).
    Использует FastEmbed (ONNX) для быстрой работы на CPU.
    """

    def __init__(self, model_path: str, model_name: str = "intfloat/multilingual-e5-small"):
        os.makedirs(model_path, exist_ok=True)

        self.model_path = model_path
        self.model_name = model_name

        system_logger.info(
            f"[Vector DB] Инициализация локальной embedding модели: {self.model_name}."
        )

        # Передаем cache_dir
        # FastEmbed сам создаст внутри этой папки подпапку с названием модели
        self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_path)

        system_logger.info(
            f"[Vector DB] Embedding модель готова к работе (путь: {self.model_path})."
        )

    async def get_embedding(self, text: str) -> list[float]:
        """
        Асинхронная обертка для генерации вектора.
        Используем asyncio.to_thread, чтобы синхронный FastEmbed не заблокировал event_loop агента!
        """
        if not self.model:
            raise RuntimeError("Ошибка: модель не инициализирована.")

        # FastEmbed возвращает генератор, берем первый элемент и конвертируем в list
        embedding_generator = await asyncio.to_thread(self.model.embed, text)
        embeddings_list = list(embedding_generator)

        return embeddings_list[0].tolist()

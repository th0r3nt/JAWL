"""
Инструментарий для извлечения поисковых "якорей" (Anchors) из сырого текста.

Поддерживает два движка извлечения (Паттерн Стратегия):
1. FlashText: Алгоритм Ахо-Корасик. $O(N)$. Сверхбыстрый, но требует точного совпадения (без учета падежей).
2. RapidFuzz: Нечеткий поиск (Fuzzy Matching). Находит морфологически измененные слова ("Стива Джобса" -> "Стив Джобс"), но работает медленнее.

P.S. "Ахо-Корасик". Черт, как же брутально.
"""

import re
from typing import List, Set
from flashtext import KeywordProcessor
from rapidfuzz import fuzz


class EntityExtractor:
    """
    Извлекатель поисковых якорей из текста для подсистемы Vector-Graph RAG.
    """

    def __init__(self, max_query_chars: int = 200, engine: str = "flashtext") -> None:
        """
        Инициализирует экстрактор.

        Args:
            max_query_chars: Максимальное количество символов в одном текстовом чанке
                             (предотвращает смысловое размытие вектора при Embedding).
            engine: 'flashtext' или 'rapidfuzz'.
        """

        self.max_query_chars = max_query_chars
        self.engine = engine.lower()

        # Для FlashText
        self._keyword_processor = KeywordProcessor(case_sensitive=False)
        # Для RapidFuzz
        self._vocab: List[str] = []

    def extract_vector_queries(self, raw_text: str) -> List[str]:
        """
        Дробит длинный текст на короткие запросы (ориентируясь на предложения),
        чтобы избежать семантического размытия вектора при поиске в Qdrant.

        Args:
            raw_text: Входящий сырой текст.

        Returns:
            Список строковых чанков, оптимизированных для Embedding-модели.
        """

        text = raw_text.strip()
        if not text:
            return []

        if len(text) <= self.max_query_chars:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        current_chunk = ""

        for s in sentences:
            if len(s) > self.max_query_chars:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = ""
                for i in range(0, len(s), self.max_query_chars):
                    chunks.append(s[i : i + self.max_query_chars])
                continue

            if len(current_chunk) + len(s) <= self.max_query_chars:
                current_chunk += s + " "
            else:
                chunks.append(current_chunk.strip())
                current_chunk = s + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    def build_graph_vocabulary(self, graph_node_names: List[str]) -> None:
        """
        Строит или обновляет внутренние словари для алгоритмов извлечения.

        Args:
            graph_node_names: Список точных имен узлов из графовой БД.
        """

        if self.engine == "flashtext":
            self._keyword_processor = KeywordProcessor(case_sensitive=False)
            for name in graph_node_names:
                # ФИКС: меняем > 2 на >= 2, чтобы аббревиатуры из 2 букв (ИИ, IT, OS) попадали в словарь
                if len(name.strip()) >= 2:
                    self._keyword_processor.add_keyword(name.strip(), name.strip())
        else:
            # Для RapidFuzz просто кэшируем список
            self._vocab = [name.strip() for name in graph_node_names if len(name.strip()) >= 2]

    def extract_graph_nodes(self, raw_text: str) -> Set[str]:
        """
        Ищет упоминания существующих графовых узлов в сыром тексте,
        используя выбранный в настройках алгоритм (FlashText или RapidFuzz).

        Args:
            raw_text: Текст для анализа (например, ответ из векторной БД или мысли агента).

        Returns:
            Множество (Set) уникальных имен узлов, найденных в тексте.
        """

        if not raw_text.strip():
            return set()

        if self.engine == "flashtext":
            return set(self._keyword_processor.extract_keywords(raw_text))
        else:
            return self._extract_rapidfuzz(raw_text)

    def _extract_rapidfuzz(self, raw_text: str) -> Set[str]:
        """
        Медленный, но умный (Fuzzy) поиск сущностей.
        Отлично справляется с русским языком (падежи и склонения).
        """

        found = set()
        text_lower = raw_text.lower()

        # Извлекаем все отдельные слова (буквы и цифры) для точного поиска коротких аббревиатур
        # Это избавляет от платформозависимых багов с границами слов (\b) для кириллицы в регулярках
        words = set(re.findall(r"\w+", text_lower))

        for node in self._vocab:
            node_lower = node.lower()

            if len(node_lower) <= 3:
                # Ищем точное совпадение слова
                if node_lower in words:
                    found.add(node)
            else:
                # partial_ratio ищет подстроку `node_lower` внутри `text_lower`.
                # Порог 80.0 позволяет сматчить "Стива Джобса" со "Стив Джобс".
                score = fuzz.partial_ratio(node_lower, text_lower)
                if score >= 80.0:
                    found.add(node)

        return found

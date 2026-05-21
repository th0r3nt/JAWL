"""
Toolset for extracting search anchors from raw text.

Supports two extraction engines (Strategy Pattern):
1. FlashText: Aho-Corasick algorithm, O(N) complexity. Highly efficient but requires exact string matches.
2. RapidFuzz: Fuzzy matching. Detects grammatical inflections and cases (essential for Russian morphology).
"""

import re
from typing import List, Set
from flashtext import KeywordProcessor
from rapidfuzz import fuzz


class EntityExtractor:
    """
    Search anchors extractor for the Vector-Graph RAG subsystem.
    """

    def __init__(self, max_query_chars: int = 200, engine: str = "flashtext") -> None:
        """
        Initializes the extractor.

        Args:
            max_query_chars: Character limit per single text chunk (prevents semantic dilution).
            engine: Extraction engine, 'flashtext' or 'rapidfuzz'.
        """

        self.max_query_chars = max_query_chars
        self.engine = engine.lower()

        self._keyword_processor = KeywordProcessor(case_sensitive=False)
        self._vocab: List[str] = []

    def extract_vector_queries(self, raw_text: str) -> List[str]:
        """
        Splits raw text into short, sentence-aware queries to prevent semantic
        dilution prior to vector embedding generation.

        Args:
            raw_text: Raw incoming string.

        Returns:
            List[str]: List of vector-safe text chunks.
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
        Builds or updates lookup vocabularies for both extractors.

        Args:
            graph_node_names: Exact node identifiers extracted from GraphDB.
        """

        if self.engine == "flashtext":
            self._keyword_processor = KeywordProcessor(case_sensitive=False)
            for name in graph_node_names:
                if len(name.strip()) >= 2:
                    self._keyword_processor.add_keyword(name.strip(), name.strip())
        else:
            self._vocab = [name.strip() for name in graph_node_names if len(name.strip()) >= 2]

    def extract_graph_nodes(self, raw_text: str) -> Set[str]:
        """
        Scans raw text to match references of existing graph nodes.

        Args:
            raw_text: Raw input string.

        Returns:
            Set[str]: Uniquely identified matches.
        """

        if not raw_text.strip():
            return set()

        if self.engine == "flashtext":
            return set(self._keyword_processor.extract_keywords(raw_text))
        else:
            return self._extract_rapidfuzz(raw_text)

    def _extract_rapidfuzz(self, raw_text: str) -> Set[str]:
        """
        Fuzzy matching parser. Handles inflections and cases.
        """

        found = set()
        text_lower = raw_text.lower()

        words = set(re.findall(r"\w+", text_lower))

        for node in self._vocab:
            node_lower = node.lower()

            if len(node_lower) <= 3:
                if node_lower in words:
                    found.add(node)
            else:
                score = fuzz.partial_ratio(node_lower, text_lower)
                if score >= 80.0:
                    found.add(node)

        return found

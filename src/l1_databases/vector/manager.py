"""
Facade for the vector memory layer.

Orchestrates Qdrant client startup, ONNX Embedding model loading,
and assembly of CRUD controllers for knowledge, thoughts, and Code Graph.
"""

from pathlib import Path

from src.l1_databases.vector.db import VectorDB
from src.l1_databases.vector.embedding import EmbeddingModel
from src.l1_databases.vector.collections import VectorCollection
from src.l1_databases.vector.management.knowledge import VectorKnowledge
from src.l1_databases.vector.management.thoughts import VectorThoughts
from src.l1_databases.vector.management.code_ast import VectorCodeAST


class VectorManager:
    """
    Facade for the vector memory layer.
    Encapsulates initialization of the Qdrant client, FastEmbed model, and CRUD handlers.
    """

    def __init__(
        self,
        db_path: Path,
        embedding_model_path: Path,
        embedding_model_name: str,
        vector_size: int = 384,
        similarity_threshold: float = 0.43,
        timezone: int = 0,
    ) -> None:
        """
        Initializes the vector DB facade.

        Args:
            db_path: Path to the Qdrant storage.
            embedding_model_path: Path to the FastEmbed models cache.
            embedding_model_name: Model name (e.g., 'intfloat/multilingual-e5-large').
            vector_size: Vector dimension.
            similarity_threshold: Cosine similarity threshold for filtering out irrelevant noise.
            timezone: Timezone offset.
        """

        self.collection_name_knowledge = "knowledge"
        self.collection_name_thoughts = "thoughts"
        self.collection_name_code_ast = "code_ast"

        self.db = VectorDB(
            db_path=str(db_path),
            collections=[
                self.collection_name_knowledge,
                self.collection_name_thoughts,
                self.collection_name_code_ast,
            ],
            vector_size=vector_size,
        )
        self.embedding = EmbeddingModel(
            model_path=str(embedding_model_path), model_name=embedding_model_name
        )

        knowledge_col = VectorCollection(self.db, self.collection_name_knowledge)
        thoughts_col = VectorCollection(self.db, self.collection_name_thoughts)
        code_ast_col = VectorCollection(self.db, self.collection_name_code_ast)

        # Pass timezone to CRUD handlers

        self.knowledge = VectorKnowledge(
            db=self.db,
            collection=knowledge_col,
            embedding_model=self.embedding,
            similarity_threshold=similarity_threshold,
            timezone=timezone,
        )
        self.thoughts = VectorThoughts(
            db=self.db,
            collection=thoughts_col,
            embedding_model=self.embedding,
            similarity_threshold=similarity_threshold,
            timezone=timezone,
        )

        self.code_ast = VectorCodeAST(
            db=self.db,
            collection=code_ast_col,
            embedding_model=self.embedding,
            similarity_threshold=similarity_threshold,
        )

    async def connect(self) -> None:
        """Opens connection to Qdrant and creates data structures."""
        await self.db.connect()

    async def disconnect(self) -> None:
        """Safely closes connection to Qdrant."""
        await self.db.disconnect()

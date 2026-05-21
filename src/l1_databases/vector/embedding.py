"""
Embedding Model Wrapper.

Wrapper over the FastEmbed library (ONNX).
Responsible for generating numerical vectors (embeddings) from text
strictly locally on the host machine's CPU, saving money and guaranteeing privacy.
"""

import os
import shutil
import asyncio
from fastembed import TextEmbedding

from src.utils.logger import main_logger


class EmbeddingModel:
    """
    Class for generating vector representations (embeddings).
    Uses FastEmbed (ONNX) for fast performance on CPU.
    Has a built-in recovery mechanism in case of cache corruption.
    """

    def __init__(
        self, model_path: str, model_name: str = "intfloat/multilingual-e5-small"
    ) -> None:
        """
        Initializes and downloads (if necessary) the ONNX model.
        Contains a built-in Fallback: in case of model file corruption, automatically wipes the cache
        and downloads the weights again.

        Args:
            model_path: Directory for storing model weights.
            model_name: Model identifier in the FastEmbed repository.
        """

        os.makedirs(model_path, exist_ok=True)

        self.model_path = model_path
        self.model_name = model_name

        main_logger.info(f"[Vector DB] Initializing local embedding model: {self.model_name}.")

        try:
            # Try to load the model from cache (or download)
            self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_path)

        except Exception as e:
            # If an error is caught (e.g. ONNXRuntimeError: NO_SUCHFILE), it means the cache is corrupted
            main_logger.warning(
                f"[Vector DB] Detected embedding model file corruption ({e}). "
                "Clearing cache and re-downloading."
            )
            # Wipe the folder with the corrupted cache
            shutil.rmtree(self.model_path, ignore_errors=True)
            os.makedirs(self.model_path, exist_ok=True)

            # Attempt to initialize (and download) again
            self.model = TextEmbedding(model_name=self.model_name, cache_dir=self.model_path)

        main_logger.info(f"[Vector DB] Embedding model is ready (path: {self.model_path}).")

    async def get_embedding(self, text: str) -> list[float]:
        """
        Synthesizes an embedding for the passed text.
        Executed in a separate thread (asyncio.to_thread) so that heavy ONNXRuntime
        computations do not block the asynchronous Event Loop of the agent core.

        Args:
            text: Incoming text for vectorization.

        Returns:
            Generated list of floats (tensor).

        Raises:
            RuntimeError: If the model has not been successfully loaded.
        """

        if not self.model:
            raise RuntimeError("Error: model is not initialized.")

        # FastEmbed returns a generator, take the first element and convert to list
        embedding_generator = await asyncio.to_thread(self.model.embed, text)
        embeddings_list = list(embedding_generator)

        return embeddings_list[0].tolist()

    async def get_embeddings_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generates embeddings for an array of strings simultaneously (Batching).
        Used in the GraphRAG mechanism to drastically speed up vectorization
        of multiple queries (neural networks process batches orders of magnitude faster).

        Args:
            texts: List of texts for vectorization.

        Returns:
            List of lists of floats (tensors).

        Raises:
            RuntimeError: If the model is not initialized.
        """

        if not self.model:
            raise RuntimeError("Error: model is not initialized.")

        if not texts:
            return []

        # FastEmbed supports passing a list of strings
        embedding_generator = await asyncio.to_thread(self.model.embed, texts)

        # Convert numpy array generator to a regular Python list of lists
        return [emb.tolist() for emb in embedding_generator]

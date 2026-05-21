# Vector Databases and Embedding Models

The semantic memory module (Vector DB) utilizes a combination of Qdrant and FastEmbed. Indexing, storage, and vector generation are performed completely locally on the host CPU, guaranteeing absolute privacy.

## Selecting the Embedding Model

The model is defined by the `embedding_model` parameter. Changing the model affects search accuracy, generation speed, and RAM consumption.

### Recommended Models:

1. **`intfloat/multilingual-e5-large`** (Most Powerful)
   - Languages: 100+
   - Vector Size (`vector_size`): 1024
   - RAM consumption: ~2.2 GB
   - Cosine threshold (`similarity_threshold`): recommended `0.85`
   - *Characteristics:* High-fidelity semantic matching, but requires more CPU resources and time for generating embeddings.

2. **`sentence-transformers/paraphrase-multilingual-mpnet-base-v2`** (Balanced)
   - Vector Size (`vector_size`): 768
   - RAM consumption: ~1.0 GB
   - Cosine threshold (`similarity_threshold`): recommended `0.75`

3. **`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`** (Lightweight)
   - Vector Size (`vector_size`): 384
   - RAM consumption: ~300 MB
   - Cosine threshold (`similarity_threshold`): recommended `0.65`
   - *Characteristics:* Optimal for low-resource VPS servers. Fast, but might miss complex associations.

## ⚠️ Critical Warning When Changing Models

The vector database architecture **does not allow mixing vectors of different dimensions**.
If you decide to change the model (for example, switching from `MiniLM` to `e5-large`), you must:
1. Change the `embedding_model` parameter in the configuration.
2. Change the `vector_size` parameter to match the new model's dimensions (for example, from 384 to 1024).
3. **Absolutely delete the database directory:** `src/utils/local/data/vector/db`.
Upon the next launch, the system will automatically recreate clean collections with correct tensor dimensions. Old data will be lost.
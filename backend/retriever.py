"""
Retriever module for the SHL Assessment Recommender.

Provides:
  - build_index()  — One-time: load catalog → embed → persist to ChromaDB
  - load_index()   — Load persisted ChromaDB collection
  - retrieve()     — Semantic search: embed query → top-n similar assessments

Embedding model: sentence-transformers/all-MiniLM-L6-v2 (384-dim, local, no API cost)
Vector DB:       ChromaDB (in-process, cosine distance, persisted to disk)

Source: PRD Section 8 (RAG Pipeline) and Section 14 Steps 2 & 7.
"""

from __future__ import annotations

import json
import logging
import os

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Embedding model (lazy singleton — never load at import time)
# ---------------------------------------------------------------------------
_model: SentenceTransformer | None = None

COLLECTION_NAME = "shl_catalog"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        logger.info("Loading embedding model '%s' ...", EMBEDDING_MODEL_NAME)
        _model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("Embedding model loaded (dim=%d)", _model.get_sentence_embedding_dimension())
    return _model


def chroma_settings() -> Settings:
    """Shared Chroma client settings (no telemetry; quieter logs on Render)."""
    return Settings(anonymized_telemetry=False)


# ---------------------------------------------------------------------------
# Build index (one-time)
# ---------------------------------------------------------------------------
def build_index(catalog_path: str, persist_path: str) -> None:
    """
    Build a ChromaDB vector index from catalog.json.

    For each assessment, creates a document string:
        "{name}. {description}. Test type: {test_type}. Levels: {job_levels}"

    Embeds with all-MiniLM-L6-v2 and stores in ChromaDB collection "shl_catalog"
    with metadata: {name, url, test_type, job_levels, description}.

    Args:
        catalog_path: Path to catalog.json.
        persist_path: Directory where ChromaDB persists its data.
    """
    # Load catalog
    logger.info("Loading catalog from %s ...", catalog_path)
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    logger.info("Loaded %d assessments", len(catalog))

    model = get_model()

    # Prepare documents, embeddings, metadata, and IDs
    documents = []
    metadatas = []
    ids = []

    for i, item in enumerate(catalog):
        name = item.get("name", "")
        description = item.get("description", "")
        test_types = item.get("test_type", [])
        job_levels = item.get("job_levels", [])
        url = item.get("url", "")

        # Test type can be a list of codes — join them
        test_type_str = ", ".join(test_types) if isinstance(test_types, list) else str(test_types)
        job_levels_str = ", ".join(job_levels) if isinstance(job_levels, list) else str(job_levels)

        # Build document string (PRD Section 14 Step 2)
        doc = f"{name}. {description}. Test type: {test_type_str}. Levels: {job_levels_str}"
        documents.append(doc)

        # Metadata — ChromaDB requires flat values (str, int, float, bool)
        metadatas.append({
            "name": name,
            "url": url,
            "test_type": test_type_str,
            "job_levels": job_levels_str,
            "description": description[:500],  # Truncate long descriptions for metadata
        })

        # Unique ID per item
        ids.append(f"assessment_{i}")

    # Embed all documents in one batch
    logger.info("Embedding %d documents ...", len(documents))
    embeddings = model.encode(documents, show_progress_bar=True, normalize_embeddings=True)
    embeddings_list = embeddings.tolist()

    # Create / reset ChromaDB collection
    os.makedirs(persist_path, exist_ok=True)
    client = chromadb.PersistentClient(path=persist_path, settings=chroma_settings())

    # Delete existing collection if present (fresh rebuild)
    try:
        client.delete_collection(COLLECTION_NAME)
        logger.info("Deleted existing collection '%s'", COLLECTION_NAME)
    except ValueError:
        pass  # Collection doesn't exist yet

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    # Upsert in batches (ChromaDB handles batching internally, but let's be safe)
    BATCH_SIZE = 100
    for start in range(0, len(documents), BATCH_SIZE):
        end = min(start + BATCH_SIZE, len(documents))
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=embeddings_list[start:end],
            metadatas=metadatas[start:end],
        )

    logger.info("Indexed %d assessments into collection '%s'", collection.count(), COLLECTION_NAME)
    logger.info("Persisted to %s", persist_path)


# ---------------------------------------------------------------------------
# Load index
# ---------------------------------------------------------------------------
def load_index(
    persist_path: str,
    client: chromadb.PersistentClient | None = None,
) -> chromadb.Collection:
    """
    Load a persisted ChromaDB collection.

    Args:
        persist_path: Directory where ChromaDB data is persisted.
        client: Optional existing PersistentClient (e.g. from lifespan with Settings).

    Returns:
        The 'shl_catalog' Collection object.

    Raises:
        ValueError: If the collection doesn't exist.
    """
    if client is None:
        client = chromadb.PersistentClient(path=persist_path, settings=chroma_settings())
    collection = client.get_collection(name=COLLECTION_NAME)
    logger.info("Loaded collection '%s' with %d items", COLLECTION_NAME, collection.count())
    return collection


# ---------------------------------------------------------------------------
# Retrieve
# ---------------------------------------------------------------------------
def retrieve(collection: chromadb.Collection, query: str, n: int = 20) -> list[dict]:
    """
    Semantic similarity search against the catalog index.

    1. Embeds the query with all-MiniLM-L6-v2
    2. Queries ChromaDB for top-n results (cosine similarity)
    3. Returns list of metadata dicts with keys:
       {name, url, test_type, description, job_levels}

    Args:
        collection: ChromaDB Collection object (from load_index).
        query:      Natural-language search query.
        n:          Number of results to return (default 20).

    Returns:
        List of dicts sorted by relevance (most similar first).
    """
    model = get_model()
    query_embedding = model.encode([query], normalize_embeddings=True).tolist()

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(n, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    # Unpack ChromaDB results (they come as lists of lists)
    items = []
    if results["metadatas"] and results["metadatas"][0]:
        for meta, doc, dist in zip(
            results["metadatas"][0],
            results["documents"][0],
            results["distances"][0],
        ):
            items.append({
                "name": meta.get("name", ""),
                "url": meta.get("url", ""),
                "test_type": meta.get("test_type", ""),
                "description": meta.get("description", ""),
                "job_levels": meta.get("job_levels", ""),
                "distance": round(dist, 4),
            })

    return items


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-7s | %(message)s")

    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    catalog_path = os.path.join(data_dir, "catalog.json")
    persist_path = os.path.join(data_dir, "chroma_db")

    if not os.path.exists(catalog_path):
        print(f"❌ catalog.json not found at {catalog_path} — run scraper.py first")
        sys.exit(1)

    print("=" * 60)
    print("Retriever self-test")
    print("=" * 60)

    # Build index
    print("\n[1] Building index ...")
    build_index(catalog_path, persist_path)

    # Load index
    print("\n[2] Loading index ...")
    collection = load_index(persist_path)
    print(f"  ✅ Collection has {collection.count()} items")

    # Test retrieval
    test_queries = [
        "Java developer mid-level programming skills",
        "leadership assessment for senior manager",
        "cognitive ability test for graduates",
        "personality assessment",
    ]

    print("\n[3] Testing retrieval ...")
    for query in test_queries:
        results = retrieve(collection, query, n=5)
        print(f"\n  Query: \"{query}\"")
        for i, r in enumerate(results):
            print(f"    {i+1}. {r['name']} (type={r['test_type']}, dist={r['distance']})")

    print(f"\n{'=' * 60}")
    print("✅ All retriever tests passed")
    print(f"{'=' * 60}")

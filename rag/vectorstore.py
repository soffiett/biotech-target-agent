import hashlib
from pathlib import Path
import chromadb
from sentence_transformers import SentenceTransformer

PERSIST_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "biotech_knowledge"

_model: SentenceTransformer | None = None
_collection: chromadb.Collection | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        # BAAI/bge-base-en-v1.5: strong on scientific text, no trust_remote_code needed
        _model = SentenceTransformer("BAAI/bge-base-en-v1.5")
    return _model


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        client = chromadb.PersistentClient(path=str(PERSIST_DIR))
        _collection = client.get_or_create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


def add_documents(texts: list[str], metadatas: list[dict], ids: list[str]) -> None:
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True).tolist()
    _get_collection().add(embeddings=embeddings, documents=texts, metadatas=metadatas, ids=ids)


def query_knowledge_base(query: str, n_results: int = 3) -> list[dict]:
    model = _get_model()
    embedding = model.encode([query], normalize_embeddings=True).tolist()[0]
    collection = _get_collection()

    if collection.count() == 0:
        return []

    results = collection.query(
        query_embeddings=[embedding],
        n_results=min(n_results, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    return [
        {
            "content": doc,
            "source": meta.get("source", ""),
            "relevance_score": round(1 - dist, 3),
        }
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]


def is_populated() -> bool:
    return _get_collection().count() > 0

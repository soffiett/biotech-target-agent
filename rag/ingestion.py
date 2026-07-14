import hashlib
from pathlib import Path
from rag.vectorstore import add_documents, is_populated

DATA_DIR = Path(__file__).parent / "data"

# Files injected directly into prompts — excluded from ChromaDB to avoid
# polluting retrieval with synthesis-specific instructions.
_PROMPT_INJECTED = {"synthesis_skill.md"}


def ingest_static_documents() -> None:
    """Load curated markdown files into ChromaDB. No-op if already populated."""
    if is_populated():
        return

    texts, metadatas, ids = [], [], []

    for md_file in sorted(DATA_DIR.glob("*.md")):
        if md_file.name in _PROMPT_INJECTED:
            continue
        content = md_file.read_text(encoding="utf-8")
        for i, chunk in enumerate(_chunk_markdown(content)):
            if len(chunk.strip()) < 50:
                continue
            doc_id = hashlib.md5(f"{md_file.name}:{i}".encode()).hexdigest()
            texts.append(chunk)
            metadatas.append({"source": md_file.stem, "chunk": i})
            ids.append(doc_id)

    if texts:
        add_documents(texts, metadatas, ids)
        n_files = len([f for f in DATA_DIR.glob("*.md") if f.name not in _PROMPT_INJECTED])
        print(f"[RAG] Ingested {len(texts)} chunks from {n_files} files")


def _chunk_markdown(content: str, max_chars: int = 900) -> list[str]:
    """Split on ## headers; further split oversized sections by paragraph."""
    sections: list[str] = []
    current: list[str] = []

    for line in content.splitlines():
        if line.startswith("## ") and current:
            sections.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        sections.append("\n".join(current))

    chunks: list[str] = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Split large sections by blank line
            paragraphs = section.split("\n\n")
            buf = ""
            for para in paragraphs:
                if len(buf) + len(para) > max_chars and buf:
                    chunks.append(buf.strip())
                    buf = para
                else:
                    buf = f"{buf}\n\n{para}" if buf else para
            if buf:
                chunks.append(buf.strip())

    return chunks

# scripts/build_faiss.py
import os
import json
import faiss
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

load_dotenv()

BASE       = os.path.dirname(os.path.dirname(__file__))
KB_PATH    = os.path.join(BASE, "app", "data", "kb.md")
INDEX_DIR  = os.path.join(BASE, "app", "data", "faiss_index")

# Mismo modelo que en retriever.py
_EMB = SentenceTransformer("all-MiniLM-L6-v2")

def chunk_text(text: str, chunk_size=600, overlap=60):
    text = text.strip()
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        if end == n:
            break
        start = max(end - overlap, 0)
    return chunks

def main():
    if not os.path.exists(KB_PATH):
        raise FileNotFoundError(f"{KB_PATH} not found")

    with open(KB_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    chunks = chunk_text(content)
    if not chunks:
        raise ValueError("kb.md está vacío")

    # Embeddings locales normalizados
    vecs = _EMB.encode(chunks, normalize_embeddings=True, convert_to_numpy=True).astype("float32")

    # Index para similitud coseno (dot product con vectores normalizados)
    index = faiss.IndexFlatIP(vecs.shape[1])
    index.add(vecs)

    os.makedirs(INDEX_DIR, exist_ok=True)
    faiss.write_index(index, os.path.join(INDEX_DIR, "kb.index"))

    meta = [{"id": i, "text": chunks[i]} for i in range(len(chunks))]
    with open(os.path.join(INDEX_DIR, "kb_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"Built FAISS index with {len(chunks)} chunks at {INDEX_DIR}")

if __name__ == "__main__":
    main()

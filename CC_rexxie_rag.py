#!/usr/bin/env python3
"""CC_rexxie_rag.py — Build and serve RAG index for Rexxie.
Indexes Obsidian vault + REX docs. Serves search on :9777.
"""
import json, os, sys
from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

VAULT = Path.home() / "Documents/GHS-Vault"
REX = Path.home() / "Desktop/REX"
DB_PATH = Path.home() / "Desktop/REX/.rexxie_rag_db"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50

def chunk_text(text, size=CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    words = text.split()
    chunks = []
    i = 0
    while i < len(words):
        chunk = " ".join(words[i:i + size])
        if chunk.strip():
            chunks.append(chunk)
        i += size - overlap
    return chunks

def clean_source(path):
    """Strip backup prefixes so the same logical file gets the same source tag."""
    p = str(path)
    while "CC_backups/" in p:
        p = p.split("CC_backups/", 1)[-1]
        # Remove date prefix
        parts = p.split("/", 1)
        if len(parts) > 1 and parts[0].startswith("pre_"):
            p = parts[1]
    return p

def build_index():
    print("Loading embedding model...")
    model = SentenceTransformer(EMBEDDING_MODEL)
    
    if DB_PATH.exists():
        import shutil
        shutil.rmtree(DB_PATH)
    
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_or_create_collection("rexxie_knowledge")
    
    seen_hashes = set()
    docs = []
    chunk_counter = 0
    
    # Index Obsidian vault (skip backup dirs)
    for md in VAULT.rglob("*.md"):
        if "CC_backups" in str(md) or ".trash" in str(md) or ".obsidian" in str(md):
            continue
        try:
            text = md.read_text()
            if len(text) < 50:
                continue
            h = hash(text)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            chunks = chunk_text(text)
            for chunk in chunks:
                docs.append({
                    "id": f"o{chunk_counter}",
                    "text": chunk,
                    "source": clean_source(md.relative_to(VAULT))
                })
                chunk_counter += 1
        except Exception:
            pass
    
    # Index REX docs (skip backup dirs, venvs, dbs)
    SKIP_RX = {"CC_backups", ".rag_venv", "logs", ".rexxie_rag_db", "__pycache__", ".git",
               "GOJ_Backups", "node_modules"}
    for md in REX.rglob("*.md"):
        path_str = str(md)
        if any(s in path_str for s in SKIP_RX):
            continue
        try:
            text = md.read_text()
            if len(text) < 50:
                continue
            h = hash(text)
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            chunks = chunk_text(text)
            for chunk in chunks:
                docs.append({
                    "id": f"r{chunk_counter}",
                    "text": chunk,
                    "source": clean_source(f"REX/{md.relative_to(REX)}")
                })
                chunk_counter += 1
        except Exception:
            pass
    
    print(f"Indexing {len(docs)} chunks...")
    
    # Batch insert
    batch_size = 100
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        texts = [d["text"] for d in batch]
        ids = [d["id"] for d in batch]
        metas = [{"source": d["source"]} for d in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()
        collection.add(embeddings=embeddings, documents=texts, ids=ids, metadatas=metas)
        if i % 500 == 0:
            print(f"  {i}/{len(docs)}")
    
    print(f"✅ Index built: {len(docs)} chunks in {DB_PATH}")
    return collection.count()

# FastAPI search server
app = FastAPI()
model = None
collection = None

@app.on_event("startup")
async def startup():
    global model, collection
    model = SentenceTransformer(EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(DB_PATH))
    collection = client.get_collection("rexxie_knowledge")
    print(f"RAG server ready — {collection.count()} chunks indexed")

@app.get("/search")
async def search(q: str, n: int = 5):
    if not collection:
        return JSONResponse({"error": "Not initialized"}, 503)
    embedding = model.encode(q).tolist()
    results = collection.query(query_embeddings=[embedding], n_results=n)
    hits = []
    for i in range(min(n, len(results["documents"][0]))):
        hits.append({
            "source": results["metadatas"][0][i]["source"],
            "text": results["documents"][0][i][:300]
        })
    return {"query": q, "results": hits}

@app.get("/health")
async def health():
    return {"status": "ok", "chunks": collection.count() if collection else 0}

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--build":
        count = build_index()
        print(f"Total chunks: {count}")
    else:
        uvicorn.run(app, host="127.0.0.1", port=9777)

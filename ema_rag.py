"""Lightweight local RAG (retrieval-augmented generation) knowledge base.

ONE shared store under ``~/cae_projekte/_rag`` with a per-document **category** so the
two consumers can keep their material apart while sharing the infrastructure:

- ``maschinen`` — technical + geometric data of e-machines judged "good"; retrieved by
  ``ema_text2ema.derive`` to ground the text→design derivation on real references.
- ``doku``      — technical documentation; retrieved by ``ema_chat`` so the assistant can
  cite deposited manuals/notes.

Embeddings come from a local Ollama embedding model (``nomic-embed-text`` by default) via
the REST API — no extra Python ML deps. Documents are chunked, each chunk embedded once
at ingest; retrieval is cosine similarity (numpy) over the in-memory index. PDF text is
extracted with ``pypdf`` (txt/md/csv are read directly).

Storage layout (single JSON index, embeddings inline as float lists):
    {"schema_version": 1,
     "documents": [{"id","title","category","source","created","n_chunks","chars"}],
     "chunks":    [{"doc_id","idx","text","embedding":[...]}]}
"""

import io
import json
import os
import time
import urllib.request

import numpy as np

OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"            # local Ollama embedding model
# ONE shared knowledge base: documents are NOT split into separate pools. The two
# consumers (text→design and chat) retrieve from the WHOLE base and differ only by
# their system prompt. `category` survives as an OPTIONAL free-form tag for the user's
# own organisation (and stats) — it no longer filters retrieval by default.
DEFAULT_CATEGORY = "allgemein"

RAG_ROOT  = os.path.expanduser("~/cae_projekte/_rag")
INDEX_PATH = os.path.join(RAG_ROOT, "index.json")

_CHUNK_CHARS   = 900
_CHUNK_OVERLAP = 150


# ── persistence ──────────────────────────────────────────────────────────────

def _load() -> dict:
    if os.path.exists(INDEX_PATH):
        try:
            with open(INDEX_PATH) as f:
                d = json.load(f)
            d.setdefault("documents", [])
            d.setdefault("chunks", [])
            return d
        except Exception:
            pass
    return {"schema_version": 1, "documents": [], "chunks": []}


def _save(idx: dict) -> None:
    os.makedirs(RAG_ROOT, exist_ok=True)
    tmp = INDEX_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(idx, f, ensure_ascii=False)
    os.replace(tmp, INDEX_PATH)


# ── embeddings (Ollama) ──────────────────────────────────────────────────────

def embed(text: str, model: str = EMBED_MODEL, timeout: int = 60) -> list[float]:
    """Single embedding via Ollama /api/embeddings."""
    body = json.dumps({"model": model, "prompt": text}).encode("utf-8")
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/embeddings", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    vec = resp.get("embedding")
    if not vec:
        raise RuntimeError("Ollama lieferte kein Embedding (Modell installiert?)")
    return vec


def _embed_many(texts: list[str], progress_cb=None) -> list[list[float]]:
    out = []
    for i, t in enumerate(texts):
        out.append(embed(t))
        if progress_cb:
            progress_cb(i + 1, len(texts))
    return out


# ── chunking + extraction ────────────────────────────────────────────────────

def _chunk(text: str) -> list[str]:
    """Split into ~_CHUNK_CHARS pieces with overlap, preferring paragraph breaks."""
    text = (text or "").strip()
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) + 2 <= _CHUNK_CHARS:
            cur = (cur + "\n\n" + p) if cur else p
        else:
            if cur:
                chunks.append(cur)
            # paragraph longer than a chunk → hard-split with overlap
            if len(p) > _CHUNK_CHARS:
                i = 0
                while i < len(p):
                    chunks.append(p[i:i + _CHUNK_CHARS])
                    i += _CHUNK_CHARS - _CHUNK_OVERLAP
                cur = ""
            else:
                cur = p
    if cur:
        chunks.append(cur)
    return chunks


def extract_text(filename: str, raw: bytes) -> str:
    """Plain text from an uploaded file. PDF via pypdf; txt/md/csv decoded directly."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        return "\n\n".join((pg.extract_text() or "") for pg in reader.pages).strip()
    # text-like
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


# ── public API ───────────────────────────────────────────────────────────────

def add_text(text: str, title: str, category: str = DEFAULT_CATEGORY, source: str = "",
             progress_cb=None) -> dict:
    """Chunk + embed a text document and append it to the (single) store.
    `category` is an optional free-form tag; it does not partition the base."""
    category = (category or DEFAULT_CATEGORY).strip() or DEFAULT_CATEGORY
    chunks = _chunk(text)
    if not chunks:
        raise ValueError("Leerer Text — nichts zu hinterlegen")
    vecs = _embed_many(chunks, progress_cb=progress_cb)

    idx = _load()
    doc_id = f"{int(time.time()*1000):x}"
    idx["documents"].append({
        "id": doc_id, "title": title or "(ohne Titel)", "category": category,
        "source": source, "created": time.strftime("%Y-%m-%d %H:%M"),
        "n_chunks": len(chunks), "chars": len(text),
    })
    for i, (c, v) in enumerate(zip(chunks, vecs)):
        idx["chunks"].append({"doc_id": doc_id, "idx": i, "text": c, "embedding": v})
    _save(idx)
    return {"id": doc_id, "title": title, "category": category, "n_chunks": len(chunks)}


def add_file(filename: str, raw: bytes, category: str = DEFAULT_CATEGORY, title: str = "",
             progress_cb=None) -> dict:
    text = extract_text(filename, raw)
    if not text.strip():
        raise ValueError(f"Kein Text aus {filename} extrahierbar")
    return add_text(text, title or filename, category, source=filename,
                    progress_cb=progress_cb)


def search(query: str, category: str | None = None, k: int = 5,
           min_score: float = 0.2) -> list[dict]:
    """Top-k chunks by cosine similarity, optionally filtered to one category."""
    idx = _load()
    rows = idx["chunks"]
    if category:
        doc_cat = {d["id"]: d["category"] for d in idx["documents"]}
        rows = [r for r in rows if doc_cat.get(r["doc_id"]) == category]
    if not rows:
        return []
    qv = np.asarray(embed(query), dtype=np.float32)
    qn = qv / (np.linalg.norm(qv) + 1e-9)
    M = np.asarray([r["embedding"] for r in rows], dtype=np.float32)
    Mn = M / (np.linalg.norm(M, axis=1, keepdims=True) + 1e-9)
    sims = Mn @ qn
    order = np.argsort(-sims)[:k]
    titles = {d["id"]: d["title"] for d in idx["documents"]}
    out = []
    for i in order:
        s = float(sims[i])
        if s < min_score:
            continue
        r = rows[i]
        out.append({"text": r["text"], "score": round(s, 3),
                    "doc_id": r["doc_id"], "title": titles.get(r["doc_id"], "")})
    return out


def context_for(query: str, category: str | None = None, k: int = 5,
                max_chars: int = 4000) -> str:
    """Retrieved snippets formatted for injection into an LLM prompt (or '' if none).
    `category=None` (default) searches the WHOLE shared base."""
    hits = search(query, category=category, k=k)
    if not hits:
        return ""
    parts, total = [], 0
    for h in hits:
        block = f"[Quelle: {h['title']}]\n{h['text']}"
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block)
    return "\n\n---\n\n".join(parts)


def list_documents() -> list[dict]:
    return _load()["documents"]


def delete_document(doc_id: str) -> bool:
    return delete_documents([doc_id]) > 0


def delete_documents(ids) -> int:
    """Delete one or many documents (and their chunks) in a single index write.
    Returns the number of documents actually removed."""
    ids = set(ids or [])
    if not ids:
        return 0
    idx = _load()
    before = len(idx["documents"])
    idx["documents"] = [d for d in idx["documents"] if d["id"] not in ids]
    idx["chunks"] = [c for c in idx["chunks"] if c["doc_id"] not in ids]
    _save(idx)
    return before - len(idx["documents"])


def stats() -> dict:
    idx = _load()
    by_cat = {}
    for d in idx["documents"]:
        c = d.get("category", DEFAULT_CATEGORY)
        by_cat[c] = by_cat.get(c, 0) + 1
    return {"n_documents": len(idx["documents"]), "n_chunks": len(idx["chunks"]),
            "by_category": by_cat, "embed_model": EMBED_MODEL}

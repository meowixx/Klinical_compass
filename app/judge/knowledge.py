"""Guideline fragments with a hybrid search: bge-m3 vectors + BM25 on lemmas, fused and reranked."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from app.judge.text import lemmas

BASE_DIR = Path(__file__).resolve().parent.parent.parent
GUIDELINES_DIR = BASE_DIR / "knowledge" / "guidelines"
RRF_K = 60
CANDIDATES = 50


@dataclass
class Hit:
    chunk: dict
    score: float  # reranker relevance, 0..1

    def reference(self) -> dict:
        c = self.chunk
        return {
            "chunk_id": c["id"],
            "doc_id": c["doc_id"],
            "doc_title": c["doc_title"],
            "section": c["section"],
            "section_title": c["section_title"],
            "subsection": c.get("subsection"),
            "kind": c["kind"],
            "uur": c.get("uur"),
            "udd": c.get("udd"),
            "page": c.get("page"),
            "url": f"https://cr.minzdrav.gov.ru/view-cr/{c['doc_id']}",
            "text": c["text"],
            "score": round(self.score, 3),
        }


def heading(chunk: dict) -> str:
    text = f"{chunk['doc_title']}. {chunk['section']} {chunk['section_title']}"
    return f"{text}. {chunk['subsection']}" if chunk.get("subsection") else text


def passage(chunk: dict, by_id: dict[str, dict]) -> str:
    """Text the models see: heading + thesis (+ its parent for a comment, + start of its comment)."""
    parts = [heading(chunk)]
    parent = by_id.get(chunk.get("parent_id") or "")
    if chunk["kind"] == "comment" and parent:
        parts.append(parent["text"][:300])
    parts.append(chunk["text"])
    if chunk["kind"] == "recommendation" and chunk.get("comment"):
        parts.append(chunk["comment"][:400])
    return "\n".join(parts)


def chunks_fingerprint(chunks: list[dict]) -> str:
    return hashlib.sha256("\n".join(c["id"] + c["text"] for c in chunks).encode()).hexdigest()[:16]


class Knowledge:
    def __init__(self, documents: list[dict], chunks: list[dict], embedder, reranker, vectors: np.ndarray | None = None):
        self.documents = {d["doc_id"]: d for d in documents}
        self.chunks = chunks
        self.by_id = {c["id"]: c for c in chunks}
        self.embedder = embedder
        self.reranker = reranker
        self.passages = [passage(c, self.by_id) for c in chunks]
        self.bm25 = BM25Okapi([lemmas(p) or ["_"] for p in self.passages])
        self.vectors = vectors if vectors is not None else embedder.encode(self.passages)

    @classmethod
    def load(cls, embedder, reranker, directory: Path = GUIDELINES_DIR) -> "Knowledge":
        documents = json.loads((directory / "documents.json").read_text(encoding="utf-8"))
        chunks = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        meta_path, vectors_path = directory / "index.json", directory / "embeddings.npy"
        if not vectors_path.exists():
            raise FileNotFoundError("Индекс КР не построен: python -m app.judge build-index")
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta["fingerprint"] != chunks_fingerprint(chunks) or meta["model"] != embedder.name:
            raise RuntimeError("Индекс КР устарел (изменились фрагменты или модель): python -m app.judge build-index")
        return cls(documents, chunks, embedder, reranker, np.load(vectors_path).astype(np.float32))

    @staticmethod
    def build_index(embedder, directory: Path = GUIDELINES_DIR) -> int:
        chunks = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        by_id = {c["id"]: c for c in chunks}
        passages = [passage(c, by_id) for c in chunks]
        vectors = embedder.encode(passages, progress=True)
        np.save(directory / "embeddings.npy", vectors.astype(np.float16))
        meta = {"model": embedder.name, "dimensions": int(vectors.shape[1]), "chunks": len(chunks),
                "fingerprint": chunks_fingerprint(chunks)}
        (directory / "index.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        return len(chunks)

    def documents_for(self, icd_code: str | None) -> list[str]:
        """Guidelines whose ICD codes cover the patient's code (F33.1 → F32/F33 guideline)."""
        code = (icd_code or "").upper().strip()
        if not code:
            return []
        return [d for d, doc in self.documents.items()
                if any(code.startswith(c) or c.startswith(code) for c in doc["icd"])]

    def search(self, query: str, doc_ids: list[str] | None = None, section_types: tuple[str, ...] | None = None,
               top: int = 3, candidates: int = 10) -> list[Hit]:
        allowed = [i for i, c in enumerate(self.chunks)
                   if (not doc_ids or c["doc_id"] in doc_ids) and (not section_types or c["section_type"] in section_types)]
        if not allowed:
            return []
        allowed_arr = np.array(allowed)
        dense = self.vectors[allowed_arr] @ self.embedder.encode([query])[0]
        sparse = self.bm25.get_scores(lemmas(query) or ["_"])[allowed_arr]
        fused: dict[int, float] = {}
        for ranking in (np.argsort(-dense)[:CANDIDATES], np.argsort(-sparse)[:CANDIDATES]):
            for place, position in enumerate(ranking):
                index = int(allowed_arr[position])
                fused[index] = fused.get(index, 0.0) + 1 / (RRF_K + place)
        shortlist = sorted(fused, key=fused.get, reverse=True)[:candidates]
        scores = self.reranker.score(query, [self.passages[i] for i in shortlist])
        ranked = sorted(zip(shortlist, scores), key=lambda pair: pair[1], reverse=True)[:top]
        return [Hit(self.chunks[i], s) for i, s in ranked]

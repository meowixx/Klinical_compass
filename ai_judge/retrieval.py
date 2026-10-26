from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from .config import CORPUS_PATH, EMBEDDINGS_PATH, manifest, model_path
from .ollama import embed
from .text import tokens


def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return numerator / denominator if denominator else 0.0


class HybridRetriever:
    def __init__(self, corpus_path: Path = CORPUS_PATH, embeddings_path: Path = EMBEDDINGS_PATH):
        self.rows: list[dict[str, Any]] = json.loads(corpus_path.read_text(encoding="utf-8"))
        self.tokenized = [tokens(row["text"]) for row in self.rows]
        self.embeddings: list[list[float]] | None = None
        if embeddings_path.exists():
            import numpy as np
            self.embeddings = np.load(embeddings_path)["embeddings"].tolist()

    def _bm25(self, query: str, indexes: list[int]) -> list[tuple[int, float]]:
        try:
            from rank_bm25 import BM25Okapi
            docs = [self.tokenized[index] for index in indexes]
            scores = BM25Okapi(docs).get_scores(tokens(query))
            return sorted(zip(indexes, map(float, scores)), key=lambda item: item[1], reverse=True)
        except ImportError:
            query_terms = Counter(tokens(query))
            scored = []
            for index in indexes:
                terms = Counter(self.tokenized[index])
                scored.append((index, sum(min(count, terms.get(term, 0)) for term, count in query_terms.items())))
            return sorted(scored, key=lambda item: item[1], reverse=True)

    def search(self, query: str, doc_id: str | None = None, limit: int = 3, rerank: bool = False) -> list[dict[str, Any]]:
        indexes = [i for i, row in enumerate(self.rows) if not doc_id or row["docId"] == doc_id]
        if not indexes:
            return []
        candidate_limit = manifest()["retrieval"]["candidateLimit"]
        bm25 = self._bm25(query, indexes)[:candidate_limit]
        rankings = [[index for index, _ in bm25]]
        if self.embeddings:
            query_vector = embed(manifest()["ollama"]["embeddings"], [query])[0]
            semantic = sorted(indexes, key=lambda i: _cosine(query_vector, self.embeddings[i]), reverse=True)[:candidate_limit]
            rankings.append(semantic)
        rrf_k = manifest()["retrieval"]["rrfK"]
        scores: Counter[int] = Counter()
        for ranking in rankings:
            for rank, index in enumerate(ranking, 1):
                scores[index] += 1 / (rrf_k + rank)
        candidates = [index for index, _ in scores.most_common(candidate_limit)]
        if rerank:
            candidates = self._rerank(query, candidates)
        output = []
        for index in candidates[:limit]:
            item = dict(self.rows[index])
            item["score"] = round(float(scores[index]), 6)
            output.append(item)
        return output

    def _rerank(self, query: str, indexes: list[int]) -> list[int]:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch
        path = model_path("reranker")
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).eval()
        pairs = [[query, self.rows[index]["text"]] for index in indexes]
        encoded = tokenizer(pairs, padding=True, truncation=True, max_length=512, return_tensors="pt")
        with torch.inference_mode():
            values = model(**encoded).logits.view(-1).float().tolist()
        return [index for index, _ in sorted(zip(indexes, values), key=lambda item: item[1], reverse=True)]


def build_embeddings(batch_size: int = 16) -> int:
    import numpy as np
    rows = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    vectors: list[list[float]] = []
    model = manifest()["ollama"]["embeddings"]
    for offset in range(0, len(rows), batch_size):
        vectors.extend(embed(model, [row["text"] for row in rows[offset:offset + batch_size]]))
        print(f"Embedded {min(offset + batch_size, len(rows))}/{len(rows)}", flush=True)
    EMBEDDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(EMBEDDINGS_PATH, embeddings=np.asarray(vectors, dtype=np.float32))
    return len(vectors)

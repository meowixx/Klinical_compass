"""The three models of the judge. Each is loaded on first use and runs on GPU when available.

Tests replace them with lightweight objects that have the same methods.
"""
import os
from functools import cached_property

import numpy as np

EMBEDDING_MODEL = os.getenv("JUDGE_EMBEDDING_MODEL", "BAAI/bge-m3")
RERANKER_MODEL = os.getenv("JUDGE_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
NLI_MODEL = os.getenv("JUDGE_NLI_MODEL", "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7")
MAX_LENGTH = 1024
RERANKER_MAX_LENGTH = 512  # a thesis fits; longer pairs make CPU reranking several times slower


def device() -> str:
    import torch

    return os.getenv("JUDGE_DEVICE") or ("cuda" if torch.cuda.is_available() else "cpu")


class Embedder:
    name = EMBEDDING_MODEL

    @cached_property
    def model(self):
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(EMBEDDING_MODEL, device=device())
        model.max_seq_length = MAX_LENGTH
        return model

    def encode(self, texts: list[str], batch_size: int = 16, progress: bool = False) -> np.ndarray:
        vectors = self.model.encode(texts, batch_size=batch_size, normalize_embeddings=True,
                                    convert_to_numpy=True, show_progress_bar=progress)
        return vectors.astype(np.float32)


class Reranker:
    @cached_property
    def model(self):
        from sentence_transformers import CrossEncoder

        return CrossEncoder(RERANKER_MODEL, max_length=RERANKER_MAX_LENGTH, device=device())

    def score(self, query: str, passages: list[str]) -> list[float]:
        """Relevance of each passage to the query, 0..1."""
        if not passages:
            return []
        scores = self.model.predict([(query, p) for p in passages], batch_size=8)
        scores = np.asarray(scores, dtype=np.float32)
        if scores.min() < 0 or scores.max() > 1:  # raw logits from an older activation default
            scores = 1 / (1 + np.exp(-scores))
        return scores.tolist()


class NLI:
    @cached_property
    def pipeline(self):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(NLI_MODEL)
        model = AutoModelForSequenceClassification.from_pretrained(NLI_MODEL).to(device()).eval()
        labels = {i: label.lower() for i, label in model.config.id2label.items()}
        return tokenizer, model, labels, torch

    def scores(self, premise: str, hypothesis: str) -> dict[str, float]:
        """Probabilities of entailment / neutral / contradiction of the hypothesis given the premise."""
        tokenizer, model, labels, torch = self.pipeline
        inputs = tokenizer(premise, hypothesis, truncation=True, max_length=512, return_tensors="pt").to(model.device)
        with torch.no_grad():
            probabilities = torch.softmax(model(**inputs).logits[0], dim=-1).tolist()
        return {labels[i]: p for i, p in enumerate(probabilities)}

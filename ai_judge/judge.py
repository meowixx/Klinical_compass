from __future__ import annotations

from typing import Any

from .config import manifest, model_path
from .retrieval import HybridRetriever
from .text import split_sentences


def quote_similarity(quote: str, source: str) -> float:
    try:
        from rapidfuzz.fuzz import partial_ratio
        return float(partial_ratio(quote, source))
    except ImportError:
        quote_words = set(quote.casefold().split())
        return 100 * len(quote_words & set(source.casefold().split())) / max(1, len(quote_words))


class ClinicalJudge:
    def __init__(self, retriever: HybridRetriever | None = None, use_nli: bool = False):
        self.retriever = retriever or HybridRetriever()
        self.use_nli = use_nli
        self._nli = None

    def verify(self, answer: str, citations: list[dict[str, Any]] | None = None, doc_id: str | None = None) -> dict[str, Any]:
        citations = citations or []
        threshold = manifest()["judge"]["quoteSimilarityThreshold"]
        citation_checks = []
        for citation in citations:
            chunk = next((row for row in self.retriever.rows if row["chunkId"] == citation.get("chunkId")), None)
            similarity = quote_similarity(citation.get("quote", ""), chunk["text"] if chunk else "")
            citation_checks.append({**citation, "similarity": round(similarity, 1), "valid": bool(chunk and similarity >= threshold)})

        claims = []
        for sentence in split_sentences(answer):
            if len(sentence) < 25:
                continue
            sources = self.retriever.search(sentence, doc_id=doc_id, limit=1)
            best = sources[0] if sources else None
            status, nli = ("supported" if best else "unverified"), None
            if best and self.use_nli:
                nli = self._classify_nli(best["text"], sentence)
                status = "rejected" if nli["label"] == "contradiction" else ("supported" if nli["label"] == "entailment" else "needs_review")
            claims.append({"claim": sentence, "status": status, "source": best, "nli": nli})

        rejected = sum(item["status"] == "rejected" for item in claims)
        invalid_quotes = sum(not item["valid"] for item in citation_checks)
        ratio = (rejected + invalid_quotes) / max(1, len(claims) + len(citation_checks))
        return {
            "decision": "reject" if ratio >= manifest()["judge"]["rejectWholeAnswerRatio"] else "review",
            "claims": claims,
            "citations": citation_checks,
            "rejectedRatio": round(ratio, 3),
        }

    def _classify_nli(self, premise: str, hypothesis: str) -> dict[str, Any]:
        if self._nli is None:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            path = model_path("nli")
            self._nli = (
                AutoTokenizer.from_pretrained(path, local_files_only=True),
                AutoModelForSequenceClassification.from_pretrained(path, local_files_only=True).eval(),
            )
        import torch
        tokenizer, model = self._nli
        encoded = tokenizer(premise, hypothesis, return_tensors="pt", truncation=True, max_length=512)
        with torch.inference_mode():
            probabilities = torch.softmax(model(**encoded).logits[0], dim=-1)
        labels = {int(index): label.casefold() for index, label in model.config.id2label.items()}
        best = int(probabilities.argmax())
        label = labels.get(best, str(best))
        label = "entailment" if "entail" in label else ("contradiction" if "contrad" in label else "neutral")
        return {"label": label, "score": round(float(probabilities[best]), 4)}

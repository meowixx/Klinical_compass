"""Judge: verification of the AI complaint analysis against the patient's words and the guidelines.

    from app.judge import get_judge, JudgeRequest, render_text
    result = get_judge().verify(JudgeRequest.model_validate({"patient": ..., "draft": ...}))
    text = render_text(result)
"""
from functools import lru_cache

from app.judge.render import render_text
from app.judge.schemas import Draft, JudgeRequest, Patient
from app.judge.verifier import Judge, Thresholds


@lru_cache(maxsize=1)
def get_judge() -> Judge:
    """Loads the guideline index, the register and the three models once per process."""
    from app.judge.grls import MedicineIndex
    from app.judge.knowledge import Knowledge
    from app.judge.models import NLI, Embedder, Reranker

    knowledge = Knowledge.load(Embedder(), Reranker())
    treatment = [c["text"] + " " + c.get("comment", "") for c in knowledge.chunks if c["section_type"] == "treatment"]
    return Judge(knowledge, NLI(), MedicineIndex.load(treatment))


__all__ = ["Draft", "Judge", "JudgeRequest", "Patient", "Thresholds", "get_judge", "render_text"]

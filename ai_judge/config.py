from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "ai_judge_models.json"
SOURCE_CORPUS = ROOT / "app" / "knowledge_database_RAG" / "clinical_guidelines_clean.json"
DATA_DIR = ROOT / "data" / "ai_judge"
CORPUS_PATH = DATA_DIR / "guideline_chunks.json"
EMBEDDINGS_PATH = DATA_DIR / "guideline_embeddings.npz"


def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def model_path(name: str) -> Path:
    return ROOT / manifest()["huggingFace"][name]["path"]

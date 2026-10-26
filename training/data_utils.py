"""Dataset/token alignment checks usable without CUDA or training libraries."""
import hashlib
import json
from pathlib import Path

def load_split(root: Path, split: str) -> list[dict]:
    if split not in ("train", "validation"):
        raise ValueError("The training pipeline must not open the held-out test split.")
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    path = root / f"{split}.jsonl"
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][path.name]:
        raise ValueError(f"Checksum mismatch: {path.name}. Rebuild and validate the dataset.")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(rows) != manifest["splits"][split] or not rows:
        raise ValueError(f"Incorrect count in {split}.")
    for row in rows:
        messages = row.get("messages", [])
        if [m.get("role") for m in messages] != ["system", "user", "assistant"]:
            raise ValueError("Expected exactly system/user/assistant, in this order.")
        if any(not isinstance(m.get("content"), str) or not m["content"].strip() for m in messages):
            raise ValueError("Every message must have nonempty text content.")
    return rows

def tokenize_example(tokenizer, row: dict, limit: int) -> dict:
    messages = row["messages"]
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=True, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if full[:len(prompt)] != prompt:
        raise ValueError("Chat template is not prefix-preserving; refusing an incorrect loss mask.")
    if not prompt or len(full) <= len(prompt):
        raise ValueError("Missing assistant target.")
    if len(full) > limit:
        raise ValueError(f"Example has {len(full)} tokens, exceeds {limit}. No automatic truncation is allowed.")
    return {"input_ids": full, "attention_mask": [1]*len(full),
            "labels": [-100]*len(prompt) + full[len(prompt):]}

def assistant_span(labels: list[int]) -> tuple[int,int]:
    start = next((i for i,x in enumerate(labels) if x != -100), -1)
    if start <= 0 or any(x == -100 for x in labels[start:]):
        raise ValueError("Expected one unpadded assistant span after a masked prompt.")
    # The logit at start-1 predicts the first target token. The last input logit is unused.
    return start, len(labels)-start+1

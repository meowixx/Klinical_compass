from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(RuntimeError):
    pass


def request(path: str, payload: dict[str, Any] | None = None, timeout: int = 180) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:11434{path}", data=body,
        headers={"Content-Type": "application/json"}, method="GET" if body is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise OllamaError(f"Ollama request {path} failed: {exc}") from exc


def embed(model: str, inputs: list[str]) -> list[list[float]]:
    return request("/api/embed", {"model": model, "input": inputs, "truncate": True})["embeddings"]

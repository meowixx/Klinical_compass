"""Loopback-only inference. No patient prompts or generated text are logged."""
import hashlib
import json
import os
from pathlib import Path
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock
from inference import QwenAdapter, ROOT

PROFILE = ROOT / "config/ai_runtime.local.json"


def validate_profile(profile):
    if profile.get("enabled") is not True or profile.get("blocked") is True:
        raise ValueError("Adapter runtime is not enabled")
    run = (ROOT / profile["run"]).resolve()
    if not run.is_relative_to(ROOT / "training/runs"):
        raise ValueError("Run must be inside training/runs")
    actual_hash = hashlib.sha256((run / "adapter/adapter_model.safetensors").read_bytes()).hexdigest()
    if actual_hash != profile["adapterSha256"]:
        raise ValueError("Adapter changed since evaluation")
    review = json.loads((ROOT / profile["review"]).read_text(encoding="utf-8"))
    if review.get("adapterSha256") != actual_hash or review.get("engineeringDeploymentApproved") is not True:
        raise ValueError("Evaluation review does not approve this adapter")
    return run, actual_hash


def main():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    run, actual_hash = validate_profile(profile)
    engine = QwenAdapter(run)
    gate = Lock()
    token = secrets.token_urlsafe(32)
    model_name = profile["model"]

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass

        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def authorized(self):
            return not self.headers.get("Origin") and secrets.compare_digest(
                self.headers.get("Authorization", ""), "Bearer " + token)

        def do_GET(self):
            if self.path == "/health":
                return self.reply(200, {"status": "ready", "provider": "local_adapter", "model": model_name,
                                        "adapterSha256": actual_hash})
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            if self.path == "/api/tags":
                return self.reply(200, {"models": [{"name": model_name}]})
            return self.reply(404, {"error": "Not found"})

        def do_POST(self):
            if not self.authorized():
                return self.reply(401, {"error": "Unauthorized"})
            if self.path != "/api/chat":
                return self.reply(404, {"error": "Not found"})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.reply(415, {"error": "JSON required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 131072:
                    return self.reply(413, {"error": "Invalid body size"})
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict) or payload.get("model") != model_name or payload.get("stream") is not False:
                    raise ValueError("Expected configured model and stream=false")
                messages = payload.get("messages")
                if not gate.acquire(blocking=False):
                    return self.reply(429, {"error": "Model is busy; retry later"})
                try:
                    output = engine.generate(messages, max_new_tokens=512)
                finally:
                    gate.release()
                if output["truncated"] or not output["text"]:
                    return self.reply(502, {"error": "Model did not return a complete answer"})
                return self.reply(200, {"model": model_name, "done": True,
                                        "message": {"role": "assistant", "content": output["text"]}})
            except (ValueError, TypeError, KeyError, AttributeError):
                return self.reply(400, {"error": "Invalid inference request"})
            except Exception as error:
                print(f"Inference failed: {type(error).__name__}", flush=True)
                engine.torch.cuda.empty_cache()
                return self.reply(503, {"error": "Inference unavailable"})

    server = ThreadingHTTPServer(("127.0.0.1", 11435), Handler)
    state = ROOT / ".run"
    state.mkdir(exist_ok=True)
    (state / "ai-adapter.token").write_text(token, encoding="ascii")
    (state / "ai-adapter.pid").write_text(str(os.getpid()), encoding="ascii")
    print(f"READY: {model_name} on http://127.0.0.1:11435", flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        (state / "ai-adapter.pid").unlink(missing_ok=True)
        (state / "ai-adapter.token").unlink(missing_ok=True)


if __name__ == "__main__":
    main()

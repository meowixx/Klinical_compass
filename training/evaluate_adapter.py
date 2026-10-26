"""Generate paired held-out answers; expected answers are never sent to the model."""
import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from inference import QwenAdapter, ROOT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    run = Path(args.run).resolve()
    config = json.loads((run / "run_config.json").read_text(encoding="utf-8"))
    dataset = ROOT / config["dataset"]
    manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    raw = (dataset / "test.jsonl").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["files"]["test.jsonl"]
    rows = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x.strip()]
    ids = json.loads((dataset / "test_ids.json").read_text(encoding="utf-8"))
    assert len(rows) == len(ids) == manifest["splits"]["test"]
    directory = run / ("evaluation-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    directory.mkdir()
    metadata = {"startedAt": datetime.now(timezone.utc).isoformat(), "baseModel": config["model"],
                "revision": config["revision"], "adapterSha256": hashlib.sha256((run / "adapter/adapter_model.safetensors").read_bytes()).hexdigest(),
                "testSha256": hashlib.sha256(raw).hexdigest(), "generation": {"do_sample": False, "max_new_tokens": 512, "max_time": 90},
                "status": "running", "clinicalApproval": False}
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print(f"Evaluation: {directory}", flush=True)
    try:
        engine = QwenAdapter(run)
        for index, (case_id, row) in enumerate(zip(ids, rows), 1):
            result = {"id": case_id, "input": row["messages"][:-1], "reference": row["messages"][-1]["content"]}
            for variant, enabled in (("base", False), ("adapter", True)):
                result[variant] = engine.generate(row["messages"][:-1], adapter=enabled)
                print(f"{index}/{len(ids)} {case_id} {variant}: {result[variant]['generatedTokens']} tokens, {result[variant]['seconds']}s", flush=True)
            with (directory / "answers.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False) + "\n")
                handle.flush()
    except BaseException as error:
        metadata["status"] = "interrupted" if isinstance(error, KeyboardInterrupt) else "failed"
        metadata["errorType"] = type(error).__name__
        (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        raise
    metadata["status"] = "completed"
    metadata["completedAt"] = datetime.now(timezone.utc).isoformat()
    (directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    print("Generation completed. Answers require review; this is not an automatic approval.", flush=True)


if __name__ == "__main__":
    main()

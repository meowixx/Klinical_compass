from __future__ import annotations

import json
import sys
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> int:
    project_root = Path(sys.argv[1]).resolve()
    manifest_path = Path(sys.argv[2]).resolve()
    config = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, item in config["huggingFace"].items():
        target = project_root / item["path"]
        print(f"Downloading {name}: {item['id']}@{item['revision']} -> {target}", flush=True)
        snapshot_download(
            repo_id=item["id"],
            revision=item["revision"],
            local_dir=target,
            allow_patterns=["*.json", "*.safetensors", "*.model", "*.txt", "LICENSE", "README.md"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

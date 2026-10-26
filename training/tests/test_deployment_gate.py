import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import serve_adapter


class DeploymentGateTests(unittest.TestCase):
    def test_failed_review_or_changed_weights_cannot_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "training/runs/test"
            (run / "adapter").mkdir(parents=True)
            weights = run / "adapter/adapter_model.safetensors"
            weights.write_bytes(b"test fixture, not model weights")
            digest = hashlib.sha256(weights.read_bytes()).hexdigest()
            review_path = root / "review.json"
            profile = {"enabled": True, "run": "training/runs/test", "adapterSha256": digest, "review": "review.json"}
            with patch.object(serve_adapter, "ROOT", root):
                review_path.write_text(json.dumps({"adapterSha256": digest, "engineeringDeploymentApproved": False}))
                with self.assertRaisesRegex(ValueError, "does not approve"):
                    serve_adapter.validate_profile(profile)
                review_path.write_text(json.dumps({"adapterSha256": digest, "engineeringDeploymentApproved": True}))
                self.assertEqual(serve_adapter.validate_profile(profile), (run, digest))
                weights.write_bytes(b"different weights")
                with self.assertRaisesRegex(ValueError, "changed since evaluation"):
                    serve_adapter.validate_profile(profile)

    def test_disabled_profile_cannot_start(self):
        with self.assertRaisesRegex(ValueError, "not enabled"):
            serve_adapter.validate_profile({"enabled": False})

    def test_run_outside_project_training_directory_rejected(self):
        with self.assertRaisesRegex(ValueError, "inside training/runs"):
            serve_adapter.validate_profile({"enabled": True, "run": "../unrelated"})


if __name__ == "__main__":
    unittest.main()

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"training"))
from data_utils import assistant_span, load_split, tokenize_example

class TinyTokenizer:
    def apply_chat_template(self,messages,tokenize,add_generation_prompt):
        return [10,11,12,13] if add_generation_prompt else [10,11,12,13,21,22,2]

class TrainingDataTests(unittest.TestCase):
    def test_only_assistant_tokens_have_labels(self):
        row={"messages":[{"role":"system","content":"s"},{"role":"user","content":"u"},{"role":"assistant","content":"a"}]}
        encoded=tokenize_example(TinyTokenizer(),row,20)
        self.assertEqual(encoded["labels"],[-100,-100,-100,-100,21,22,2])
        start,keep=assistant_span(encoded["labels"])
        self.assertEqual((start,keep),(4,4))
        self.assertEqual(len(encoded["input_ids"])-keep,start-1)

    def test_oversized_examples_not_truncated(self):
        with self.assertRaisesRegex(ValueError,"No automatic truncation"):
            tokenize_example(TinyTokenizer(),{"messages":[{}, {}, {}]},5)

    def test_template_prefix_mismatch_stops_training(self):
        class Broken(TinyTokenizer):
            def apply_chat_template(self,*a,**kw):
                return [98] if kw["add_generation_prompt"] else [10,21,2]
        with self.assertRaisesRegex(ValueError,"prefix-preserving"):
            tokenize_example(Broken(),{"messages":[{}, {}, {}]},20)

    def test_reject_masked_gap_or_no_prompt(self):
        for labels in ([1,2],[-100,-100],[-100,2,-100,3]):
            with self.assertRaises(ValueError): assistant_span(labels)

    def test_training_does_not_open_test_split(self):
        with self.assertRaisesRegex(ValueError,"held-out"):
            load_split(ROOT/"datasets/clinical_compass_qwen_v6","test")

    def test_actual_train_validation_checksums(self):
        root=ROOT/"datasets/clinical_compass_qwen_v6"
        self.assertEqual(len(load_split(root,"train")),52)
        self.assertEqual(len(load_split(root,"validation")),12)

    def test_compact_loss_matches_full_causal_mask_when_torch_available(self):
        if importlib.util.find_spec('torch') is None: self.skipTest('torch installs in the separate training environment')
        import torch
        import torch.nn.functional as F
        torch.manual_seed(42)
        logits=torch.randn(1,7,32,requires_grad=True)
        labels=torch.tensor([[-100,-100,-100,-100,21,22,2]])
        full=F.cross_entropy(logits[:,:-1,:].reshape(-1,32),labels[:,1:].reshape(-1),ignore_index=-100)
        start,keep=assistant_span(labels[0].tolist())
        compact=F.cross_entropy(logits[:,-keep:-1,:].reshape(-1,32),labels[:,start:].reshape(-1))
        self.assertTrue(torch.allclose(full,compact))
        grad_full=torch.autograd.grad(full,logits,retain_graph=True)[0]
        grad_compact=torch.autograd.grad(compact,logits)[0]
        self.assertTrue(torch.allclose(grad_full,grad_compact))

if __name__=="__main__": unittest.main()

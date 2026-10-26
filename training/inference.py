"""Local, pinned Qwen + LoRA inference shared by evaluation and serving."""
import json
import os
from contextlib import nullcontext
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "training/cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


class QwenAdapter:
    def __init__(self, run):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        from peft import PeftModel, prepare_model_for_kbit_training
        self.run = Path(run).resolve()
        self.config = json.loads((self.run / "run_config.json").read_text(encoding="utf-8"))
        result = json.loads((self.run / "result.json").read_text(encoding="utf-8"))
        if result["status"] != "completed":
            raise ValueError("Training run is not complete")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for this local adapter preset")
        self.torch = torch
        dtype = torch.bfloat16
        self.tokenizer = AutoTokenizer.from_pretrained(self.run / "adapter", local_files_only=True)
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                                  bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
        base = AutoModelForCausalLM.from_pretrained(
            self.config["model"], revision=self.config["revision"], local_files_only=True,
            trust_remote_code=False, quantization_config=quant, device_map={"": 0},
            torch_dtype=dtype, attn_implementation="sdpa", low_cpu_mem_usage=True)
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=False)
        for layer in (base.get_input_embeddings(), base.get_output_embeddings()):
            if layer is not None:
                layer.to(dtype=dtype)
        self.model = PeftModel.from_pretrained(base, self.run / "adapter", is_trainable=False)
        self.model.eval()
        self.model.config.use_cache = True

    def generate(self, messages, *, adapter=True, max_new_tokens=512):
        if not isinstance(messages, list) or not messages or len(messages) > 12:
            raise ValueError("Expected 1..12 messages")
        if any(m.get("role") not in ("system", "user", "assistant") or
               not isinstance(m.get("content"), str) for m in messages):
            raise ValueError("Invalid messages")
        inputs = self.tokenizer.apply_chat_template(messages, add_generation_prompt=True,
                                                    tokenize=True, return_dict=True, return_tensors="pt")
        length = inputs["input_ids"].shape[-1]
        if length + max_new_tokens > 4096:
            raise ValueError("Context exceeds 4096 tokens; refusing silent truncation")
        inputs = {k: v.to("cuda") for k, v in inputs.items()}
        started = time.perf_counter()
        with self.torch.inference_mode(), self.torch.autocast("cuda", dtype=self.torch.bfloat16), (nullcontext() if adapter else self.model.disable_adapter()):
            output = self.model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False,
                                         use_cache=True, pad_token_id=self.tokenizer.pad_token_id,
                                         eos_token_id=self.tokenizer.eos_token_id, logits_to_keep=1, max_time=90)
        tokens = output[0, length:].tolist()
        return {"text": self.tokenizer.decode(tokens, skip_special_tokens=True).strip(),
                "generatedTokens": len(tokens), "inputTokens": length,
                "truncated": not tokens or tokens[-1] != self.tokenizer.eos_token_id,
                "seconds": round(time.perf_counter() - started, 3)}

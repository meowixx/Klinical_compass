"""Single-GPU QLoRA. No automatic deployment, test-set tuning or data upload."""
from __future__ import annotations
import argparse
import importlib.metadata
import json
import os
import shutil
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("HF_HOME", str(ROOT / "training" / "cache"))
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
from data_utils import load_split, tokenize_example, assistant_span

def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+"\n", encoding="utf-8")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="Check GPU, quantization and tokenization, without downloading model weights or training.")
    args=parser.parse_args()
    config=json.loads((ROOT/"training/config.json").read_text(encoding="utf-8"))
    dataset=ROOT/config["dataset"]
    train_rows=load_split(dataset,"train")
    validation_rows=load_split(dataset,"validation")

    import torch
    import bitsandbytes as bnb
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainingArguments, set_seed
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable. Install the NVIDIA driver and CUDA PyTorch using TRAIN_MODEL.cmd.")
    torch.cuda.set_device(0)
    properties=torch.cuda.get_device_properties(0)
    free,total=torch.cuda.mem_get_info()
    print(f"GPU: {properties.name}; free {free/2**20:.0f} / {total/2**20:.0f} MiB", flush=True)
    if properties.major < 8:
        raise RuntimeError("This preset requires NVIDIA Ampere or newer (RTX 30/40/50 series).")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 is not supported by this GPU/driver. This low-memory preset cannot run.")
    # Check the actual installed Windows CUDA kernel, not just an import.
    probe=torch.randn(64,64,device="cuda",dtype=torch.bfloat16)
    packed,state=bnb.functional.quantize_4bit(probe,quant_type="nf4")
    restored=bnb.functional.dequantize_4bit(packed,quant_state=state)
    if not torch.isfinite(restored).all():
        raise RuntimeError("bitsandbytes NF4 CUDA smoke check failed.")
    del probe,packed,state,restored
    torch.cuda.empty_cache()

    tokenizer=AutoTokenizer.from_pretrained(config["model"], revision=config["revision"], trust_remote_code=False)
    if tokenizer.pad_token_id is None: tokenizer.pad_token=tokenizer.eos_token
    train=[tokenize_example(tokenizer,r,config["maxSequenceLength"]) for r in train_rows]
    validation=[tokenize_example(tokenizer,r,config["maxSequenceLength"]) for r in validation_rows]
    maximum=max(len(r["input_ids"]) for r in train+validation)
    print(f"Validated: {len(train)} train / {len(validation)} validation; max {maximum} tokens; assistant-only loss.", flush=True)
    print("The held-out test split is not used for model selection.",flush=True)
    if args.check_only:
        print("CHECK PASSED. No model weights downloaded; no training performed.",flush=True)
        return
    free,_=torch.cuda.mem_get_info()
    if free/2**20 < config["minimumFreeVramMiB"]:
        raise RuntimeError(f"Only {free/2**20:.0f} MiB GPU memory is free. Need at least {config['minimumFreeVramMiB']}. Close GPU apps; unload Ollama with: ollama stop qwen3:4b-instruct . Then retry.")

    run=ROOT/"training/runs"/(datetime.now().strftime("%Y%m%d-%H%M%S")+f"-{os.getpid()}")
    run.mkdir(parents=True,exist_ok=False)
    write_json(run/"run_config.json",config)
    shutil.copyfile(dataset/"manifest.json",run/"dataset_manifest.json")
    shutil.copyfile(dataset/"system_prompt.txt",run/"system_prompt.txt")
    write_json(run/"environment.json", {"python":sys.version,"gpu":properties.name,"cuda":torch.version.cuda,
        "versions":{p:importlib.metadata.version(p) for p in ("torch","transformers","peft","accelerate","bitsandbytes")}})
    write_json(run/"status.json",{"status":"loading","startedAt":datetime.now(timezone.utc).isoformat(),"clinicalApproval":False})
    print(f"Run folder: {run}\nDownloading/loading original base weights; first run can take time.",flush=True)
    try:
        set_seed(config["seed"])
        dtype=torch.bfloat16
        quant=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type="nf4",bnb_4bit_use_double_quant=True,bnb_4bit_compute_dtype=dtype)
        model=AutoModelForCausalLM.from_pretrained(config["model"],revision=config["revision"],trust_remote_code=False,
            quantization_config=quant,device_map={"":0},torch_dtype=dtype,attn_implementation="sdpa",low_cpu_mem_usage=True)
        model.config.use_cache=False
        model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,
                                              gradient_checkpointing_kwargs={"use_reentrant":False})
        # PEFT promotes frozen dense weights to FP32. Keep the large frozen vocabulary
        # matrices in BF16, while norms and trainable LoRA weights retain stable precision.
        for layer in (model.get_input_embeddings(),model.get_output_embeddings()):
            if layer is not None:
                if any(p.requires_grad for p in layer.parameters()):
                    raise RuntimeError("Expected frozen vocabulary weights before LoRA setup.")
                layer.to(dtype=dtype)
        model=get_peft_model(model,LoraConfig(r=config["loraRank"],lora_alpha=config["loraAlpha"],
            lora_dropout=config["loraDropout"],target_modules=config["targetModules"],bias="none",task_type="CAUSAL_LM"))
        model.print_trainable_parameters()

        def collate(batch):
            if len(batch)!=1: raise ValueError("This memory preset supports batch size 1 only.")
            return {k:torch.tensor([v],dtype=torch.long) for k,v in batch[0].items()}

        class AssistantTrainer(Trainer):
            def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
                labels=inputs["labels"]
                start,keep=assistant_span(labels[0].tolist())
                # Project only the assistant positions, not the whole long prompt, to
                # avoid allocating a [full_sequence, 151k_vocab] FP32 loss tensor.
                out=model(input_ids=inputs["input_ids"],attention_mask=inputs["attention_mask"],logits_to_keep=keep,use_cache=False)
                logits=out.logits[:,:-1,:].contiguous()
                targets=labels[:,start:].contiguous()
                loss=torch.nn.functional.cross_entropy(logits.float().reshape(-1,logits.shape[-1]),targets.reshape(-1))
                return (loss,{"loss":loss}) if return_outputs else loss

        options=TrainingArguments(output_dir=str(run/"checkpoints"),num_train_epochs=config["epochs"],
            per_device_train_batch_size=1,per_device_eval_batch_size=1,
            gradient_accumulation_steps=config["gradientAccumulationSteps"],learning_rate=config["learningRate"],
            warmup_ratio=0.1,lr_scheduler_type="cosine",max_grad_norm=1.0,weight_decay=0.01,
            bf16=True,fp16=False,optim="adamw_torch",gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant":False},eval_strategy="epoch",save_strategy="epoch",
            load_best_model_at_end=True,metric_for_best_model="eval_loss",greater_is_better=False,save_total_limit=2,
            logging_steps=1,logging_first_step=True,report_to=[],push_to_hub=False,
            dataloader_num_workers=0,dataloader_pin_memory=False,remove_unused_columns=False,
            prediction_loss_only=True,label_names=["labels"],seed=config["seed"],data_seed=config["seed"])
        trainer=AssistantTrainer(model=model,args=options,train_dataset=train,eval_dataset=validation,
                                 data_collator=collate,processing_class=tokenizer)
        trainer.model_accepts_loss_kwargs=False
        print("Measuring validation loss before training...",flush=True)
        baseline=trainer.evaluate()
        write_json(run/"baseline_metrics.json",baseline)
        # Preserve the untrained zero-delta adapter as a real baseline candidate.
        baseline_path=run/"baseline_adapter"
        trainer.save_model(str(baseline_path))
        tokenizer.save_pretrained(baseline_path)
        write_json(run/"status.json",{"status":"training","clinicalApproval":False})
        result=trainer.train()
        validation_metrics=trainer.evaluate()
        trainer.save_model(str(run/"adapter"))
        tokenizer.save_pretrained(run/"adapter")
        trainer.save_state()
        improved=validation_metrics["eval_loss"] < baseline["eval_loss"]
        summary={"status":"completed","baseModel":config["model"],"revision":config["revision"],
            "baselineValidation":baseline,"finalValidation":validation_metrics,"train":result.metrics,
            "validationLossImproved":improved,"bestCheckpoint":trainer.state.best_model_checkpoint,
            "adapter":str(run/"adapter"),"clinicalApproval":False,"deployed":False,
            "note":"Validation loss is not clinical quality; run independent test and physician review before deployment."}
        write_json(run/"result.json",summary)
        write_json(run/"status.json",{"status":"completed","clinicalApproval":False,"deployed":False})
        print(f"\nTRAINING COMPLETE\nAdapter: {run/'adapter'}\nReport: {run/'result.json'}",flush=True)
        if not improved:
            print("Validation loss did not improve over the base model. Keep the base model pending review.",flush=True)
        print("The website/Ollama model was not replaced. Adapter export and independent evaluation are separate steps.",flush=True)
    except BaseException as error:
        (run/"error.log").write_text(traceback.format_exc(),encoding="utf-8")
        write_json(run/"status.json",{"status":"interrupted" if isinstance(error,KeyboardInterrupt) else "failed","error":str(error),"deployed":False})
        if isinstance(error,torch.cuda.OutOfMemoryError):
            print("GPU MEMORY EXHAUSTED. Close other GPU apps/Ollama and retry, or use the other PC with more VRAM. No dataset truncation or CPU fallback was applied.",flush=True)
        raise

if __name__=="__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user. Completed epoch checkpoints remain in training/runs.",file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print(f"ERROR: {error}",file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)

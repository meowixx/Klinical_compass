"""Download only public tokenizer files; tokenize dataset locally, never upload cases."""
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    from jinja2.sandbox import ImmutableSandboxedEnvironment
    from tokenizers import Tokenizer
    model="Qwen/Qwen3-4B-Instruct-2507"
    cache=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/".tokenizer_cache"
    cache.mkdir(parents=True,exist_ok=True)
    with urllib.request.urlopen(f"https://huggingface.co/api/models/{model}",timeout=45) as response:
        revision=json.load(response)["sha"]
    paths={}
    for name in ("tokenizer.json","tokenizer_config.json"):
        path=cache/f"{revision}-{name}"
        if not path.exists():
            with urllib.request.urlopen(f"https://huggingface.co/{model}/resolve/{revision}/{name}",timeout=60) as response:
                path.write_bytes(response.read())
        paths[name]=path
    config=json.loads(paths["tokenizer_config.json"].read_text(encoding="utf-8"))
    tokenizer=Tokenizer.from_file(str(paths["tokenizer.json"]))
    env=ImmutableSandboxedEnvironment(trim_blocks=True,lstrip_blocks=True)
    def fail(message): raise ValueError(message)
    env.globals["raise_exception"]=fail
    template=env.from_string(config["chat_template"])
    lengths=[]
    per_split={}
    for split in ("train","validation","test"):
        entries=[json.loads(x) for x in (ROOT/f"{split}.jsonl").read_text(encoding="utf-8").splitlines()]
        lens=[]
        for row in entries:
            chat=template.render(messages=row["messages"],add_generation_prompt=False,tools=None,**{k:v for k,v in config.items() if k.endswith('_token')})
            n=len(tokenizer.encode(chat,add_special_tokens=False).ids)
            lens.append(n)
        lengths+=lens
        per_split[split]={"min":min(lens),"max":max(lens),"mean":round(sum(lens)/len(lens),1),"total":sum(lens)}
    report={"model":model,"revision":revision,"tokenizerSha256":hashlib.sha256(paths['tokenizer.json'].read_bytes()).hexdigest(),
        "chatTemplate":"official tokenizer_config.json, add_generation_prompt=False",
        "includesSystemUserAssistant":True,"count":len(lengths),"contextLimit":4096,
        "maxTokens":max(lengths),"truncatedExamples":0,"allFit":max(lengths)<=4096,"splits":per_split}
    (ROOT/"token_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(report,ensure_ascii=False))
    if not report['allFit']: raise SystemExit(1)

if __name__=="__main__": main()

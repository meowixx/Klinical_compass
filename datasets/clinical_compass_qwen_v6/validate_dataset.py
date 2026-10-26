"""Offline consistency checks. Passing is NOT evidence of clinical efficacy."""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def validate() -> dict:
    rows = json.loads((ROOT / "cases.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    sources = {s["id"] for s in json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))["sources"]}
    errors, warnings = [], []
    patients, families = defaultdict(set), defaultdict(set)
    seen_inputs, seen_pairs, ids = set(), set(), set()
    checks = 0

    def require(value, message):
        nonlocal checks
        checks += 1
        if not value:
            errors.append(message)

    partner_pattern = re.compile(r"авиандр|марит[уy]п[ие]рдин|aviandr|maritupirdine", re.I)
    forbidden_drugs = re.compile(r"фаводеглиб|эсциталопрам|пароксетин|сертралин|венлафаксин|дулоксетин|прегабалин|буспирон|кветиапин|алпразолам", re.I)
    for row in rows:
        ident, data, expected = row["id"], row["patientData"], row["expected"]
        text = expected["text"]
        require(ident not in ids, f"{ident}: duplicate ID")
        ids.add(ident)
        require(row["split"] in ("train", "validation", "test"), f"{ident}: split")
        require(row["synthetic"] is True and row["syntheticPatientId"].startswith("SYN-"), f"{ident}: provenance")
        patients[row["syntheticPatientId"]].add(row["split"])
        families[row["familyId"]].add(row["split"])
        require(row["review"]["status"] == "awaiting_clinician_review", f"{ident}: unsupported review status")
        require(all(s["id"] in sources and s["sections"] for s in row["sourceRefs"]), f"{ident}: missing source")
        require(isinstance(text,str) and 40 <= len(text) < 1700, f"{ident}: output length")
        require(text.count("?") <= 1, f"{ident}: too many questions")
        require(not forbidden_drugs.search(text), f"{ident}: competing/incorrect medication name")
        require(not re.search(r"\d+\s*(?:мг|таблет|mg)\b",text,re.I), f"{ident}: dosing")
        require("<think>" not in text and "</think>" not in text, f"{ident}: thinking trace")
        require(bool(partner_pattern.search(text)) == expected["mentionPartner"], f"{ident}: partner label")
        require(expected["urgency"] in ("routine", "prompt", "emergency"), f"{ident}: urgency")
        if expected["clarificationNeeded"]:
            require(not expected["mentionPartner"], f"{ident}: suggestion before critical clarification")
            require("?" in text or "уточните" in text.lower(), f"{ident}: missing targeted request")
        if expected["urgency"] == "emergency":
            require(not expected["mentionPartner"], f"{ident}: promotion during emergency")
            require("112" in text and "немедлен" in text.lower(), f"{ident}: emergency route missing")
            require(not expected["clarificationNeeded"], f"{ident}: blocking emergency question")
        if expected["mentionPartner"]:
            require(data.get("age",0)>18, f"{ident}: age")
            require(data.get("diagnosisCode")=="F41.1" and data.get("diagnosisConfirmedByDoctor") is True, f"{ident}: confirmed indication")
            history = data.get("treatmentHistory") or {}
            require(history.get("firstTwoLinesRefractory") is True and history.get("adequacyAndAdherenceReviewedByDoctor") is True, f"{ident}: guideline position")
            require(data.get("contraindicationsReviewed") is True and data.get("medicationsReviewedByDoctor") is True, f"{ident}: reviews")
            safety = data.get("safety") or {}
            for field in ("allergyToComponents","epilepsyOrOrganicBrainDisease","hepaticInsufficiency","pregnant","breastfeeding","galactoseLactaseMalabsorption","maoiCurrentOrLast14Days","serotonergicOrCyp2d6Interaction","sedativeCombination","alcoholUse","cardiovascularCautionUnresolved"):
                require(safety.get(field) is False, f"{ident}: {field} unresolved")
            require(safety.get("renalFunctionReviewed") is True, f"{ident}: renal review")
            gfr = safety.get("gfrMlMin")
            require((isinstance(gfr,(float,int)) and gfr>=60) or (gfr is None and bool(safety.get("renalReviewConclusion"))), f"{ident}: renal limit")
            require(data.get("riskAssessment",{}).get("acuteDanger") is False, f"{ident}: acute safety")
            require("партнёрск" in text.lower() and "врач" in text.lower(), f"{ident}: disclosure/clinician")
        raw_input = json.dumps({"taskKind":row["taskKind"],"patientData":data},ensure_ascii=False,sort_keys=True)
        require(raw_input not in seen_inputs, f"{ident}: repeated input")
        seen_inputs.add(raw_input)
        pair = hashlib.sha256((raw_input+text).encode()).hexdigest()
        require(pair not in seen_pairs, f"{ident}: repeated pair")
        seen_pairs.add(pair)
    require(all(len(v)==1 for v in families.values()), "scenario family leaks across splits")
    require(all(len(v)==1 for v in patients.values()), "synthetic patient leaks across splits")
    require(len(rows)==manifest["total"], "manifest total mismatch")
    for split in ("train","validation","test"):
        path=ROOT/f"{split}.jsonl"
        messages=[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        split_rows=[r for r in rows if r["split"]==split]
        row_ids=json.loads((ROOT/f"{split}_ids.json").read_text(encoding="utf-8"))
        require(row_ids==[r["id"] for r in split_rows],f"{split}: ID sidecar")
        require(len(messages)==len(split_rows)==manifest["splits"][split], f"{split}: count")
        require(hashlib.sha256(path.read_bytes()).hexdigest()==manifest["files"][path.name], f"{split}: checksum")
        for row,entry in zip(split_rows,messages):
            ms=entry.get("messages",[])
            require([m["role"] for m in ms]==["system","user","assistant"],f"{row['id']}: chat roles")
            if len(ms)!=3: continue
            require(ms[-1]["content"]==row["expected"]["text"],f"{row['id']}: target drift")
            payload=json.loads(ms[1]["content"])
            require(set(payload)<= {"task","patientData","requiredFormat","partnerMedicationAssessment"},f"{row['id']}: metadata leakage")
            require(payload["patientData"]==row["patientData"],f"{row['id']}: input drift")
    report={"passed":not errors,"checks":checks,"examples":len(rows),"errors":errors,"warnings":warnings,
        "splitCounts":dict(Counter(r["split"] for r in rows)),
        "patientAndFamilyLeakage":False if all(len(v)==1 for v in [*patients.values(),*families.values()]) else True,
        "clinicalApproval":False,"trainingPerformed":False,
        "limitations":["Structural checks cannot establish clinical correctness, source applicability or model safety.",
                        "Small authored holdout measures regression behavior, not real-world clinical performance."]}
    (ROOT/"validation_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__ == "__main__":
    raise SystemExit(0 if validate()["passed"] else 1)

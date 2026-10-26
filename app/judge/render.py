"""Plain text for the doctor, built from the judge result by a template (no language model)."""

MARKS = {"supported": "✅", "warning": "⚠️", "rejected": "❌"}


def reference_line(ref: dict) -> str:
    section = f"разд. {ref['section']} «{ref['section_title']}»"
    if ref.get("subsection"):
        section += f", {ref['subsection']}"
    level = f", УУР {ref['uur']}, УДД {ref['udd']}" if ref.get("uur") else ""
    page = f", стр. {ref['page']}" if ref.get("page") else ""
    return f"КР {ref['doc_id']} «{ref['doc_title']}», {section}{level}{page} — {ref['url']}"


def excerpt(text: str, limit: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def render_text(result: dict) -> str:
    lines = []
    if result["status"] == "discard":
        lines += ["❌ Черновик ИИ отклонён проверкой: большая часть утверждений не подтверждена.", ""]

    diagnosis = result["diagnosis"]
    if diagnosis.get("code"):
        docs = ", ".join(f"{d['doc_id']} «{d['title']}»" for d in diagnosis["guidelines"]) or "нет в базе"
        lines += [f"Диагноз: {diagnosis['code']} {diagnosis.get('title') or ''}".rstrip() + f". КР: {docs}", ""]

    shown = [s for s in result["symptoms"] if s["verdict"] != "rejected"]
    lines.append("Жалобы пациента (проверено по словам пациента и КР Минздрава):")
    if not shown:
        lines.append("  — подтверждённых симптомов нет")
    for s in shown:
        date = f" ({s['date']})" if s.get("date") else ""
        lines.append(f"{MARKS[s['verdict']]} {s['term']} — «{s['quote']}»{date}")
        ref = (s.get("guideline") or {}).get("reference")
        if ref:
            lines.append(f"   {reference_line(ref)}")
            lines.append(f"   «{excerpt(ref['text'])}»")
        for reason in s["reasons"]:
            lines.append(f"   ⚠️ {reason}")

    match = result.get("possible_match")
    if match and match["verdict"] != "rejected":
        lines += ["", f"{MARKS[match['verdict']]} Может соответствовать: {match['text']}"]
        if match.get("guideline"):
            lines.append(f"   {reference_line(match['guideline'])}")
        lines += [f"   ⚠️ {r}" for r in match["reasons"]]

    to_check = [t for t in result["to_check"] if t["verdict"] != "rejected"]
    if to_check:
        lines += ["", "Уточнить у пациента:"] + [f"• {t['text']}" for t in to_check]

    lines += ["", "Проверьте перед решением:"]
    for note in result["attention"] or [{"text": "дополнительных замечаний нет"}]:
        lines.append(f"• {note['text']}")
        if note.get("guideline"):
            lines.append(f"   {reference_line(note['guideline'])}")

    rejected = [s for s in result["symptoms"] if s["verdict"] == "rejected"]
    rejected += [p for p in [match] + result["to_check"] if p and p["verdict"] == "rejected"]
    if rejected:
        lines += ["", "Отклонено проверкой:"]
        for item in rejected:
            label = f"{item['term']} — «{item['quote']}»" if "term" in item else item["text"]
            lines.append(f"❌ {label}: {'; '.join(item['reasons'])}")

    if result["uncovered"]:
        lines += ["", "Не разобрано ИИ (слова пациента без симптома в черновике):"]
        lines += [f"• «{u['text']}»" + (f" ({u['date']})" if u.get("date") else "") for u in result["uncovered"]]
    return "\n".join(lines)

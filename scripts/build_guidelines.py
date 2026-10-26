"""Builds the guideline knowledge base for the judge from the Ministry of Health API.

Every guideline listed in DOCUMENTS is downloaded as structured JSON (GetClinrec),
split by sections and recommendation theses, and written to knowledge/guidelines/.
Page numbers are taken from the matching PDFs when --pdf-dir is given.

    python scripts/build_guidelines.py --pdf-dir ../A15/A15
    python scripts/build_guidelines.py --offline        # reuse knowledge/guidelines/raw
"""
import argparse
import html
import json
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = BASE_DIR / "knowledge" / "guidelines"
RAW_DIR = OUT_DIR / "raw"
CARD_URL = "https://apicr.minzdrav.gov.ru/API.ashx?op=GetClinrec&id={doc_id}"
VIEW_URL = "https://cr.minzdrav.gov.ru/view-cr/{doc_id}"
PDF_URL = "https://apicr.minzdrav.gov.ru/API.ashx?op=GetClinrecPdf&id={doc_id}"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Clinical-Compass guideline builder"

# The same set as the A15 folder: <ID>_<version>.
DOCUMENTS = ["162_3", "190_2", "295_4", "301_3", "456_3", "457_3", "617_5", "675_2", "753_1", "880_1"]

# API section id -> (section type, section number shown to the doctor).
# doc_whole holds an outdated full text, doc_bible is the bibliography; both are skipped with
# the title page, abbreviations, working group, methodology, quality criteria and patient leaflet.
SECTIONS = {
    "doc_terms": ("terms", "Термины"),
    "doc_crat_info_1_1": ("overview", "1.1"),
    "doc_crat_info_1_2": ("overview", "1.2"),
    "doc_crat_info_1_3": ("overview", "1.3"),
    "doc_crat_info_1_4": ("overview", "1.4"),
    "doc_crat_info_1_5": ("overview", "1.5"),
    "doc_crat_info_1_6": ("clinical_picture", "1.6"),
    "doc_diag_2": ("diagnosis", "2"),
    "doc_diag_2_1": ("diagnosis", "2.1"),
    "doc_diag_2_2": ("diagnosis", "2.2"),
    "doc_diag_2_3": ("diagnosis", "2.3"),
    "doc_diag_2_4": ("diagnosis", "2.4"),
    "doc_diag_2_5": ("diagnosis", "2.5"),
    "doc_3": ("treatment", "3"),
    "doc_4": ("rehabilitation", "4"),
    "doc_5": ("prevention", "5"),
    "doc_6": ("organization", "6"),
    "doc_7": ("additional", "7"),
    "doc_a3": ("reference", "Прил. А3"),
    "doc_b": ("algorithm", "Прил. Б"),
    "doc_g": ("scales", "Прил. Г"),
}

TEXT_CHUNK_CHARS = 1200
COMMENT_CHUNK_CHARS = 1000
COMMENT_IN_THESIS_CHARS = 400

LATIN_GRADE = str.maketrans("АВСавс", "ABCabc")
EVIDENCE_START_RE = re.compile(r"^\W*(уровень\s+(убедительности|достоверности)|УУР|УДД)", re.I)
UUR_RE = re.compile(r"(?:убедительности\s+рекомендаци\w*|УУР)\s*\W{0,3}\s*([ABCАВС])\b", re.I)
UDD_RE = re.compile(r"(?:достоверности\s+доказательств\w*|УДД)\s*\W{0,3}\s*([1-5])", re.I)
THESIS_START_RE = re.compile(r"^\W*(•|(не\s+)?рекоменд(уется|овано|ован|овать))", re.I)
COMMENT_RE = re.compile(r"^\W*комментари", re.I)
NUMBERED_HEADING_RE = re.compile(r"^\d+(\.\d+)+\.?\s+\S")
ICD_RE = re.compile(r"\b([A-Z]\d\d(?:\.\d{1,2})?)")


class BlockParser(HTMLParser):
    """Flattens section HTML into paragraph-level blocks: p, li, heading, table."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[dict] = []
        self.current: dict | None = None
        self.li_depth = 0
        self.table: list[list[str]] | None = None
        self.cell: list[str] | None = None

    def start(self, kind: str):
        self.finish()
        self.current = {"kind": kind, "parts": []}

    def finish(self):
        if self.current is not None:
            text = clean("".join(self.current["parts"]))
            if text:
                self.blocks.append({"kind": self.current["kind"], "text": text})
        self.current = None

    def handle_starttag(self, tag, attrs):
        if self.table is not None:
            if tag == "tr":
                self.table.append([])
            elif tag in ("td", "th"):
                self.cell = []
            elif tag == "br" and self.cell is not None:
                self.cell.append(" ")
            return
        if tag == "table":
            self.finish()
            self.table = []
        elif tag in ("h1", "h2", "h3", "h4"):
            self.start("heading")
        elif tag == "li":
            self.li_depth += 1
            self.start("li")
        elif tag == "p" and not self.li_depth:
            self.start("p")
        elif tag == "br" and self.current is not None:
            self.current["parts"].append(" ")

    def handle_endtag(self, tag):
        if self.table is not None:
            if tag in ("td", "th") and self.cell is not None and self.table:
                self.table[-1].append(clean("".join(self.cell)))
                self.cell = None
            elif tag == "table":
                rows = [" | ".join(c for c in row if c) for row in self.table]
                text = "\n".join(r for r in rows if r)
                if text:
                    self.blocks.append({"kind": "table", "text": text})
                self.table = None
            return
        if tag == "li":
            self.li_depth = max(0, self.li_depth - 1)
            self.finish()
        elif tag in ("h1", "h2", "h3", "h4") or (tag == "p" and not self.li_depth):
            self.finish()

    def handle_data(self, data):
        if self.table is not None:
            if self.cell is not None:
                self.cell.append(data)
            return
        if self.current is None:
            self.start("p")
        self.current["parts"].append(data)

    def close(self):
        super().close()
        self.finish()


def clean(text: str) -> str:
    text = html.unescape(text).replace("\xa0", " ").replace("​", "")
    return re.sub(r"[ \t\r\f\v]+", " ", re.sub(r"\s*\n\s*", "\n", text)).strip()


def html_blocks(content: str) -> list[dict]:
    parser = BlockParser()
    parser.feed(content or "")
    parser.close()
    for block in parser.blocks:
        if block["kind"] == "p" and len(block["text"]) < 150 and NUMBERED_HEADING_RE.match(block["text"]):
            block["kind"] = "heading"
    return parser.blocks


def is_evidence(block: dict) -> bool:
    text = block["text"]
    return len(text) < 300 and bool(EVIDENCE_START_RE.match(text)) and bool(UUR_RE.search(text) or UDD_RE.search(text))


def is_thesis_start(block: dict) -> bool:
    text = block["text"]
    return bool(THESIS_START_RE.match(text)) or (block["kind"] == "li" and re.search(r"рекоменд", text[:300], re.I) is not None)


def is_list_item(block: dict) -> bool:
    return bool(re.match(r"^\s*([-–—]|\d+[).]|[а-я]\))\s*\S", block["text"]))


def lead(text: str) -> str:
    """The opening of a recommendation that introduces a list of options («Рекомендуется …:»)."""
    colon = text.find(":")
    return text[:colon + 1] if 0 < colon < 400 else text[:250].rstrip() + "…"


def grade(regex: re.Pattern, text: str) -> str | None:
    match = regex.search(text)
    return match.group(1).translate(LATIN_GRADE).upper() if match else None


def split_text(text: str, limit: int) -> list[str]:
    """Splits on paragraph, then sentence boundaries so that pieces stay under limit."""
    if len(text) <= limit:
        return [text]
    units = []
    for paragraph in text.split("\n"):
        if len(paragraph) <= limit:
            units.append(paragraph)
        else:
            units.extend(re.split(r"(?<=[.;!?])\s+(?=[А-ЯA-Z0-9«(•-])", paragraph))
    pieces, current = [], ""
    for unit in units:
        while len(unit) > limit:
            cut = unit.rfind(" ", 0, limit)
            cut = cut if cut > limit // 2 else limit
            if current:
                pieces.append(current)
                current = ""
            pieces.append(unit[:cut].strip())
            unit = unit[cut:].strip()
        if current and len(current) + len(unit) + 1 > limit:
            pieces.append(current)
            current = unit
        else:
            current = f"{current}\n{unit}" if current else unit
    if current:
        pieces.append(current)
    return [p for p in pieces if p.strip()]


def section_chunks(blocks: list[dict]) -> list[dict]:
    """Groups blocks into theses (recommendation + evidence level + comment) and plain text."""
    chunks: list[dict] = []
    pending: list[dict] = []
    last_thesis: dict | None = None
    base_text = ""  # last thesis that states the recommendation itself, for list-of-options theses
    in_comment = False
    subsection = None

    def flush_text(items: list[dict]):
        if items:
            chunks.append({"kind": "text", "subsection": subsection, "text": "\n".join(b["text"] for b in items)})

    for block in blocks:
        if block["kind"] == "heading":
            flush_text(pending)
            pending, last_thesis, base_text, in_comment = [], None, "", False
            subsection = block["text"]
            continue
        if is_evidence(block):
            start = max((i for i, b in enumerate(pending) if is_thesis_start(b)), default=max(len(pending) - 1, 0))
            flush_text(pending[:start])
            body = pending[start:]
            if not body and last_thesis is not None and len(last_thesis["comment"]) > 1:
                # An option of a list («- ламотриджин») was read as the previous comment: take it back.
                comment = last_thesis["comment"]
                cut = next((i for i in range(len(comment) - 1, 0, -1) if is_thesis_start(comment[i])), None)
                if cut is None:
                    cut = len(comment)
                    while cut > 1 and is_list_item(comment[cut - 1]):
                        cut -= 1
                body, last_thesis["comment"] = comment[cut:], comment[:cut]
            if body:
                text = "\n".join(b["text"] for b in body)
                option = is_list_item(body[0]) or len(text) < 200
                if option and base_text and not re.search(r"рекоменд", text, re.I):
                    text = f"{lead(base_text)}\n{text}"
                elif re.search(r"рекоменд", text, re.I):
                    base_text = text
                last_thesis = {
                    "kind": "recommendation",
                    "subsection": subsection,
                    "text": text,
                    "uur": grade(UUR_RE, block["text"]),
                    "udd": grade(UDD_RE, block["text"]),
                    "comment": [],
                }
                chunks.append(last_thesis)
            elif last_thesis is not None and not last_thesis["uur"]:
                last_thesis["uur"] = grade(UUR_RE, block["text"])
                last_thesis["udd"] = grade(UDD_RE, block["text"])
            pending, in_comment = [], False
            continue
        if last_thesis is not None and not pending and (COMMENT_RE.match(block["text"]) or (in_comment and not is_thesis_start(block))):
            in_comment = True
            last_thesis["comment"].append(block)
            continue
        in_comment = False
        pending.append(block)
    flush_text(pending)

    # Neighbouring text blocks of one subsection are merged and re-split to a readable size.
    merged: list[dict] = []
    for chunk in chunks:
        previous = merged[-1] if merged else None
        if (chunk["kind"] == "text" and previous and previous["kind"] == "text"
                and previous["subsection"] == chunk["subsection"]
                and len(previous["text"]) + len(chunk["text"]) < TEXT_CHUNK_CHARS):
            previous["text"] += "\n" + chunk["text"]
        else:
            merged.append(chunk)
    result = []
    for chunk in merged:
        if chunk["kind"] == "text":
            result.extend({**chunk, "text": piece} for piece in split_text(chunk["text"], TEXT_CHUNK_CHARS))
        else:
            chunk["comment"] = "\n".join(b["text"] for b in chunk["comment"])
            result.append(chunk)
    return result


def normalized(text: str) -> str:
    return re.sub(r"[^а-яa-z0-9]", "", text.lower().replace("ё", "е"))


class PageLocator:
    """Finds the PDF page on which a chunk starts by matching normalized text probes."""

    def __init__(self, pdf_path: Path):
        from pypdf import PdfReader

        self.text, self.starts = "", []
        for page in PdfReader(str(pdf_path)).pages:
            self.starts.append(len(self.text))
            self.text += normalized(page.extract_text() or "")

    def page(self, chunk_text: str) -> int | None:
        target = normalized(chunk_text)
        for offset in (0, len(target) // 3, len(target) // 2):
            probe = target[offset:offset + 40]
            if len(probe) < 25:
                continue
            position = self.text.find(probe)
            if position >= 0:
                return sum(1 for start in self.starts if start <= position)
        return None


def fetch(doc_id: str, offline: bool) -> dict:
    path = RAW_DIR / f"{doc_id}.json"
    if not offline:
        request = urllib.request.Request(CARD_URL.format(doc_id=doc_id), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(request, timeout=120) as response:
            path.write_bytes(response.read())
        time.sleep(0.5)
    return json.loads(path.read_text(encoding="utf-8"))


def build_document(doc_id: str, card: dict, pdf_dir: Path | None) -> tuple[dict, list[dict]]:
    title = card["name"].strip()
    sections = {s["id"]: s for s in card["obj"]["sections"]}
    pdf = next(pdf_dir.glob(f"{doc_id}_*.pdf"), None) if pdf_dir else None
    locator = PageLocator(pdf) if pdf else None
    document = {
        "doc_id": doc_id,
        "title": title,
        "icd": sorted(set(ICD_RE.findall((card.get("mkb") or "").upper()))),
        "version": card.get("version"),
        "created": card.get("created"),
        "view_url": VIEW_URL.format(doc_id=doc_id),
        "pdf_url": PDF_URL.format(doc_id=doc_id),
    }
    chunks = []
    for section_id, (section_type, number) in SECTIONS.items():
        section = sections.get(section_id)
        if not section or not (section.get("content") or "").strip():
            continue
        section_title = re.sub(r"^\s*\d+(\.\d+)*\.?\s*", "", clean(section.get("title") or "")) or number
        for piece in section_chunks(html_blocks(section["content"])):
            parts = [(piece["text"], piece["kind"])]
            comment = piece.get("comment", "")
            if piece["kind"] == "recommendation" and len(comment) > COMMENT_IN_THESIS_CHARS:
                # Long comments are searchable on their own; the judge prefixes them with the thesis.
                parts += [(p, "comment") for p in split_text(comment, COMMENT_CHUNK_CHARS)]
            parent_id = None
            for text, kind in parts:
                chunk_id = f"{doc_id}:{section_id}:{len([c for c in chunks if c['section_id'] == section_id]):03d}"
                chunk = {
                    "id": chunk_id,
                    "doc_id": doc_id,
                    "doc_title": title,
                    "section_id": section_id,
                    "section": number,
                    "section_title": section_title,
                    "subsection": piece["subsection"],
                    "section_type": section_type,
                    "kind": kind,
                    "parent_id": parent_id if kind == "comment" else None,
                    "text": text,
                    "comment": comment if kind == "recommendation" else "",
                    "uur": piece.get("uur"),
                    "udd": piece.get("udd"),
                    "page": locator.page(text) if locator else None,
                }
                if kind == "recommendation":
                    parent_id = chunk_id
                chunks.append(chunk)
    return document, chunks


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf-dir", type=Path, help="Folder with <ID>_<version>_*.pdf for page numbers (A15).")
    parser.add_argument("--offline", action="store_true", help="Use previously downloaded JSON from raw/.")
    args = parser.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    documents, chunks = [], []
    for doc_id in DOCUMENTS:
        document, doc_chunks = build_document(doc_id, fetch(doc_id, args.offline), args.pdf_dir)
        documents.append(document)
        chunks.extend(doc_chunks)
        theses = sum(c["kind"] == "recommendation" for c in doc_chunks)
        paged = sum(c["page"] is not None for c in doc_chunks)
        print(f"{doc_id:6} {document['title'][:45]:45} фрагментов {len(doc_chunks):4}, тезисов {theses:3}, "
              f"страница найдена {paged}/{len(doc_chunks)}")
    (OUT_DIR / "documents.json").write_text(json.dumps(documents, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT_DIR / "chunks.json").write_text(json.dumps(chunks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Итого: {len(documents)} КР, {len(chunks)} фрагментов -> {OUT_DIR}")


if __name__ == "__main__":
    sys.exit(main())

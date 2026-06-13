from docx import Document
import fitz


def parse_pdf(path: str) -> list[dict]:
    doc = fitz.open(path)
    pages: list[dict] = []
    try:
        for index, page in enumerate(doc):
            text = page.get_text().strip()
            if not text:
                continue
            pages.append(
                {
                    "text": text,
                    "page": index + 1,
                    "metadata": {},
                }
            )
    finally:
        doc.close()
    return pages


def parse_docx(path: str) -> list[dict]:
    document = Document(path)
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)
    if not text:
        return []
    return [{"text": text, "page": 1, "metadata": {}}]


def parse_text(path: str) -> list[dict]:
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read().strip()
    if not text:
        return []
    return [{"text": text, "page": 1, "metadata": {}}]


def parse_file(path: str) -> list[dict]:
    ext = path.rsplit(".", 1)[-1].lower()
    if ext == "pdf":
        return parse_pdf(path)
    if ext == "docx":
        return parse_docx(path)
    return parse_text(path)  # .md, .txt, code files

"""Turn an uploaded document into plain text. No model involved."""

import zipfile
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

import pdfplumber
from docx import Document
from striprtf.striprtf import rtf_to_text

from server.finance.parser import StatementFormatError, parse_statement

SUPPORTED = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".odt": "OpenDocument",
    ".rtf": "Rich text",
    ".html": "HTML",
    ".htm": "HTML",
    ".txt": "Text",
    ".md": "Markdown",
}


class IntakeError(Exception):
    """Message is safe to show the owner."""


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def _pdf(path: Path) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


MAX_UNZIPPED = 100 * 1024 * 1024


def _zip_guard(path: Path) -> None:
    """DOCX and ODT are zips; refuse one that expands far beyond a document's size."""
    with zipfile.ZipFile(path) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
            raise IntakeError(f"{path.name}: too large when unpacked")


def _docx(path: Path) -> str:
    _zip_guard(path)
    doc = Document(str(path))
    lines = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text for cell in row.cells))
    return "\n".join(lines)


def _odt(path: Path) -> str:
    _zip_guard(path)
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("content.xml"))
    paragraphs = []
    for el in root.iter():
        if el.tag.endswith("}p") or el.tag.endswith("}h"):
            paragraphs.append("".join(el.itertext()))
    return "\n".join(paragraphs)


def _html(path: Path) -> str:
    parser = _Text()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return "".join(parser.parts)


def _plain(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


READERS = {
    ".pdf": _pdf,
    ".docx": _docx,
    ".odt": _odt,
    ".rtf": lambda p: rtf_to_text(_plain(p)),
    ".html": _html,
    ".htm": _html,
    ".txt": _plain,
    ".md": _plain,
}


def read_document(path: Path) -> str:
    reader = READERS.get(path.suffix.lower())
    if reader is None:
        raise IntakeError(
            f"{path.name}: unsupported file type (use {', '.join(sorted(SUPPORTED))})"
        )
    try:
        text = reader(path)
    except IntakeError:
        raise
    except Exception as e:
        raise IntakeError(f"{path.name}: could not be read ({type(e).__name__})") from e
    if not text.strip():
        raise IntakeError(f"no readable text in {path.name}")
    return text


def is_statement(path: Path) -> bool:
    """True for a bank statement the importer already understands; intake skips those."""
    if path.suffix.lower() != ".pdf":
        return False
    try:
        parse_statement(path)
    except StatementFormatError:
        return False
    except Exception:  # noqa: BLE001  an unreadable PDF is not a statement
        return False
    return True

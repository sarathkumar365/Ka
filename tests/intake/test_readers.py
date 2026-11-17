import zipfile
from datetime import date
from decimal import Decimal

import pytest
from docx import Document
from reportlab.pdfgen import canvas

from server.intake.readers import IntakeError, is_statement, read_document
from tests.fixtures.statement_pdf import SpecRow, StatementSpec, build_statement

TEXT = "Jane Example\nSoftware Engineer at Acme Widgets"


def make_pdf(p):
    c = canvas.Canvas(str(p))
    c.drawString(72, 700, "Jane Example")
    c.drawString(72, 680, "Software Engineer at Acme Widgets")
    c.save()


def make_docx(p):
    d = Document()
    for line in TEXT.splitlines():
        d.add_paragraph(line)
    d.save(str(p))


def make_odt(p):
    body = "".join(f"<text:p>{line}</text:p>" for line in TEXT.splitlines())
    xml = (
        '<?xml version="1.0"?><office:document-content '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
        f"<office:body><office:text>{body}</office:text></office:body></office:document-content>"
    )
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("content.xml", xml)


MAKERS = {
    ".pdf": make_pdf,
    ".docx": make_docx,
    ".odt": make_odt,
    ".rtf": lambda p: p.write_text(
        r"{\rtf1\ansi Jane Example\par Software Engineer at Acme Widgets}"
    ),
    ".html": lambda p: p.write_text(
        "<html><style>x{}</style><body><h1>Jane Example</h1><p>Software Engineer at "
        "Acme Widgets</p><script>var x=1</script></body></html>"
    ),
    ".txt": lambda p: p.write_text(TEXT),
    ".md": lambda p: p.write_text("# Jane Example\n\nSoftware Engineer at Acme Widgets"),
}


@pytest.mark.parametrize("suffix", sorted(MAKERS))
def test_each_format_returns_its_text(tmp_path, suffix):
    p = tmp_path / f"resume{suffix}"
    MAKERS[suffix](p)
    out = read_document(p)
    assert "Acme" in out and "Engineer" in out
    assert "var x" not in out


def test_bad_files_raise_readable_errors(tmp_path):
    bad = {
        "a.xyz": b"data",
        "empty.txt": b"   \n",
        "broken.docx": b"not a zip at all",
        "broken.pdf": b"%PDF-garbage",
    }
    for name, content in bad.items():
        p = tmp_path / name
        p.write_bytes(content)
        with pytest.raises(IntakeError) as e:
            read_document(p)
        assert str(e.value)


def test_statement_pdf_is_recognised(tmp_path):
    stmt, resume = tmp_path / "s.pdf", tmp_path / "r.pdf"
    rows = [SpecRow(date(2031, 3, 25), "Point of sale purchase", "Apos Cafe", Decimal("-4.50"))]
    build_statement(stmt, StatementSpec(rows=rows))
    make_pdf(resume)
    assert is_statement(stmt) is True
    assert is_statement(resume) is False


def test_zip_bomb_is_refused(tmp_path):
    p = tmp_path / "bomb.docx"
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", b"0" * (120 * 1024 * 1024))
    with pytest.raises(IntakeError, match="too large"):
        read_document(p)

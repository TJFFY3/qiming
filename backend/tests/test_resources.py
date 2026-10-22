import pytest
from backend.app.shared.tools.resources import extract_resource


def test_plain_text(tmp_path):
    path = tmp_path / "a"
    path.write_text("教材文字", encoding="utf-8")
    assert "教材文字" in extract_resource(path, "教材.txt")["text"]


def test_disguised_docx(tmp_path):
    path = tmp_path / "a"
    path.write_text("not docx")
    with pytest.raises(ValueError):
        extract_resource(path, "教材.docx")


def test_scanned_pdf(tmp_path):
    from pypdf import PdfWriter

    path = tmp_path / "scan.pdf"
    w = PdfWriter()
    w.add_blank_page(width=100, height=100)
    w.write(path)
    with pytest.raises(ValueError, match="OCR"):
        extract_resource(path, "scan.pdf")

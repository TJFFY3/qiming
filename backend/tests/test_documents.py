import json
from pathlib import Path
import pytest
from docx import Document
from backend.app.documents import DocumentEngine

SAMPLE = json.loads(Path("vendor/chemistry/examples/outline.json").read_text())


def test_draft_tables_and_no_overwrite(tmp_path):
    engine = DocumentEngine()
    assert engine.validate(SAMPLE)["outline"]["sections"]
    with pytest.raises(ValueError):
        engine.render(SAMPLE, tmp_path / "rejected", "v001", False)
    report = engine.render(SAMPLE, tmp_path / "v001", "v001", True)
    doc = Document(tmp_path / "v001/outline.docx")
    assert report["draft"]
    assert "待核验" in doc.paragraphs[0].text
    assert len(doc.tables) == 4
    assert len(doc.tables[-1].rows) == 25
    assert doc.tables[0].cell(1, 1).text == ""
    with pytest.raises(FileExistsError):
        engine.render(SAMPLE, tmp_path / "v001", "v001", True)


def test_revision_hash_and_preservation(tmp_path):
    engine = DocumentEngine()
    report = engine.render(SAMPLE, tmp_path / "v001", "v001", True)
    original = json.loads((tmp_path / "v001/content.json").read_text())
    patch = {
        "base_sha256": report["content_sha256"],
        "changes": [
            {
                "block_id": "question-1",
                "replacement": [{"type": "paragraph", "content": "新问题"}],
            }
        ],
    }
    engine.revise(tmp_path / "v001", patch, tmp_path / "v002", "v002")
    new = json.loads((tmp_path / "v002/content.json").read_text())
    assert new["sections"][1:] == original["sections"][1:]
    patch["base_sha256"] = "stale"
    with pytest.raises(ValueError):
        engine.revise(tmp_path / "v002", patch, tmp_path / "v003", "v003")

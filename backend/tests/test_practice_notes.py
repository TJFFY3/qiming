import json

import pytest
from docx import Document

from backend.app.timed_practice.tools.documents import render, validate_content
from backend.app.timed_practice.domain.requirements import resolve_requirements
from backend.tests.test_timed_practice import paper, settings, source


@pytest.mark.parametrize(
    "note", ["注：电子转移数应按化合价变化计算。", "标注：氧元素化合价由－2升至0。"]
)
def test_teaching_notes_are_preserved_and_do_not_block_word_export(tmp_path, note):
    raw = paper()
    raw["written"][0]["explanation"] = note
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    report = render(content, [source()], tmp_path / "v1", False)
    assert report["validation"]["passed"]
    assert not report["validation"]["issues"]
    assert note in "\n".join(
        p.text for p in Document(tmp_path / "v1" / "answers.docx").paragraphs
    )
    assert json.loads((tmp_path / "v1" / "generation_report.json").read_text())[
        "validation"
    ]["passed"]


def test_actual_generation_instructions_are_rejected_before_word_export():
    raw = paper()
    raw["written"][0]["explanation"] = "注：本题已修改为新题，请删除本段编辑说明。"
    with pytest.raises(ValueError, match="编辑说明"):
        validate_content(raw, resolve_requirements(settings(), ""), [source()])


def test_note_exception_does_not_disable_other_word_checks(tmp_path):
    from backend.app.timed_practice.tools.documents import validate_practice_word

    path = tmp_path / "broken.docx"
    path.write_bytes(b"not an Office package")
    report = validate_practice_word([path])
    assert not report["passed"]
    assert report["issues"]
    raw = paper()
    raw["written"][0]["explanation"] = "这里保留了题改为的编辑残留。"
    content = validate_content(raw, resolve_requirements(settings(), ""), [source()])
    with pytest.raises(ValueError, match="Word结构校验失败"):
        render(content, [source()], tmp_path / "v1", False)


def test_pipeline_repairs_internal_note_and_publishes_teaching_note(tmp_path):
    from fastapi.testclient import TestClient
    from backend.tests.test_timed_practice import app_for, PREFIX

    internal = paper()
    internal["written"][0]["explanation"] = "注：本题已修改为新题，请删除本段编辑说明。"
    fixed = paper()
    fixed["written"][0]["explanation"] = "注：电子转移数按化合价变化计算。"
    replies = [internal, fixed]
    with TestClient(app_for(tmp_path, replies)) as client:
        session = client.post(PREFIX + "/sessions", json=settings()).json()
        job = client.post(
            PREFIX + f"/sessions/{session['id']}/generate", json={"prompt": "生成"}
        ).json()
        result = client.get(PREFIX + f"/jobs/{job['id']}").json()
        assert result["status"] == "completed", result["error"]
        assert not replies
        response = client.get(
            PREFIX
            + f"/sessions/{session['id']}/versions/{result['version_id']}/files/answers"
        )
        assert response.status_code == 200

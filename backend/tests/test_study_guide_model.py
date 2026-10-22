"""Regression coverage for model output diagnostics and usable repair requests."""
import json
from pathlib import Path

import httpx
import pytest

from backend.app.config import Settings
from backend.app.study_guide.tools.documents import DocumentEngine
from backend.app.study_guide.llm.client import ModelClient
from backend.app.study_guide.application.pipeline import Pipeline
from backend.app.study_guide.storage.store import Store


def configured(tmp_path):
    return Settings(data_dir=tmp_path, model_url="https://model.test/v1",
                    model_key="TESTSECRET", model="test")


def test_invalid_json_retains_original_and_exact_location(tmp_path):
    text = '{"outline":\n{"title":"实验",}}'
    client = ModelClient(configured(tmp_path), httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {"content": text}}]})
    ))
    with pytest.raises(ValueError) as error:
        client.generate_json([])
    assert getattr(error.value, "response_text", None) == text
    assert "第2行" in str(error.value)


def test_fastgpt_configuration_error_is_not_rewritten_as_bad_json(tmp_path):
    settings = configured(tmp_path)
    client = ModelClient(settings, httpx.MockTransport(
        lambda _: httpx.Response(500, json={"code": 513001, "statusText": "modelUnConfigured"})
    ))
    with pytest.raises(ValueError, match="模型配置"):
        client.generate_json([])


def test_length_finish_is_rejected_even_when_json_is_valid(tmp_path):
    client = ModelClient(configured(tmp_path), httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{
            "message": {"content": '{"outline": {}}'}, "finish_reason": "length"}]})
    ))
    with pytest.raises(ValueError, match="截断"):
        client.generate_json([])


def test_fenced_json_with_leading_whitespace(tmp_path):
    client = ModelClient(configured(tmp_path), httpx.MockTransport(
        lambda _: httpx.Response(200, json={"choices": [{"message": {
            "content": ' \n```json\n{"outline": {}}\n```\n'}}]})
    ))
    assert client.generate_json([]) == {"outline": {}}


class Retriever:
    def search(self, query):
        return [{"id": "src", "title": "教材", "category": "textbook",
                 "evidence": "元素化合价变化", "locator": "切片1", "verified": False}]


def run_pipeline(tmp_path, handle):
    settings = configured(tmp_path)
    store = Store(tmp_path / "test.sqlite")
    session = store.create_session({"chapter": "氧化还原反应"})
    pipeline = Pipeline(settings, store, Retriever(),
                        ModelClient(settings, httpx.MockTransport(handle)), DocumentEngine())
    job = pipeline.start_generation(session["id"], {"prompt": "生成导学案"})
    pipeline.run(job["id"])
    return store, session["id"], store.get_job(job["id"])


def test_invalid_output_repair_receives_original_and_publishes_docx(tmp_path):
    invalid = '{"outline":\n{"title":"实验",}}'
    sample = json.loads(Path("vendor/chemistry/examples/outline.json").read_text())
    sent = []

    def handle(request):
        sent.append(json.loads(request.content)["messages"])
        text = invalid if len(sent) == 1 else json.dumps(sample, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})

    store, sid, job = run_pipeline(tmp_path, handle)
    assert job["status"] == "completed", job
    assert sent[1][-2] == {"role": "assistant", "content": invalid}
    assert "第2行" in sent[1][-1]["content"]
    version = store.get_session(sid)["versions"][-1]
    assert Path(version["directory"], "outline.docx").is_file()
    diagnostics = list((tmp_path / sid / "diagnostics" / job["id"]).glob("*.json"))
    assert len(diagnostics) == 1
    assert json.loads(diagnostics[0].read_text())["response_text"] == invalid


@pytest.mark.parametrize("failure", ["timeout", "http", "config", "stream"])
def test_service_errors_are_not_retried_as_content_repairs(tmp_path, failure):
    calls = []

    def handle(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("test", request=request)
        if failure == "stream":
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                content=b'data: {"choices":[{"delta":{"content":"{}"}}]}\n\n')
        if failure == "config":
            return httpx.Response(500, json={"code": 513001})
        return httpx.Response(503, json={"error": "down"})

    store, sid, job = run_pipeline(tmp_path, handle)
    assert len(calls) == 1
    assert job["status"] == "failed"
    assert "自动修复" not in job["error"]
    assert not store.get_session(sid)["versions"]


def test_unrepairable_json_keeps_retry_budget_and_parse_detail(tmp_path):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"outline":\n{"title":"TESTSECRET",}}'}}]})

    store, sid, job = run_pipeline(tmp_path, handle)
    assert len(calls) == 3
    assert job["status"] == "failed"
    assert "第2行" in job["error_detail"]
    assert not store.get_session(sid)["versions"]
    diagnostics = list((tmp_path / sid / "diagnostics" / job["id"]).glob("*.json"))
    assert len(diagnostics) == 3
    assert all("TESTSECRET" not in path.read_text() for path in diagnostics)


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [None]},
                                   {"choices": [{"message": {}}]}, []])
def test_malformed_envelope_is_a_service_error(tmp_path, body):
    from backend.app.study_guide.llm.client import ModelServiceError

    client = ModelClient(configured(tmp_path), httpx.MockTransport(
        lambda _: httpx.Response(200, json=body)
    ))
    with pytest.raises(ModelServiceError, match="响应"):
        client.generate_json([])


def test_invalid_json_in_header_repair_receives_local_original(tmp_path):
    sample = json.loads(Path("vendor/chemistry/examples/outline.json").read_text())
    sample["outline"]["sections"][0]["blocks"][1]["headers"][0] = ""
    invalid = '{"headers": ["反应",]}'
    sent = []

    def handle(request):
        sent.append(json.loads(request.content)["messages"])
        texts = [json.dumps(sample, ensure_ascii=False), invalid,
                 '{"headers": ["反应", "变化的元素", "化合价变化"]}']
        return httpx.Response(200, json={"choices": [{"message": {
            "content": texts[len(sent) - 1]}}]})

    store, sid, job = run_pipeline(tmp_path, handle)
    assert job["status"] == "completed", job
    assert len(sent) == 3
    assert sent[2][-2] == {"role": "assistant", "content": invalid}
    assert "完整导学案" not in sent[2][-1]["content"]
    assert "outline" not in json.loads(sent[2][1]["content"])
    assert store.get_session(sid)["versions"]

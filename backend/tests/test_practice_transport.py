import json
from types import SimpleNamespace

import httpx
import pytest

from backend.app.config import Settings
from backend.app.timed_practice.model_client import (
    PracticeModelClient,
    ModelOutputError,
)


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def event(data, name="answer"):
    return (
        ("event: " + name + "\n" if name else "")
        + "data: "
        + (data if isinstance(data, str) else json.dumps(data, ensure_ascii=False))
        + "\n\n"
    ).encode()


def test_fastgpt_stream_parses_answer_deltas_ignores_reasoning_and_reports_progress():
    updates = []
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        assert request.extensions["timeout"]["read"] > 120
        stream = Chunks(
            [
                b": heartbeat\n\n",
                event({"choices": [{"delta": {"reasoning_content": "内部推理"}}]}),
                event(
                    {"choices": [{"delta": {"content": "不要混入"}}]}, "flowNodeStatus"
                ),
                event({"choices": [{"delta": {"content": '```json\n{"title":'}}]}),
                event(
                    {
                        "choices": [
                            {
                                "delta": {"content": '"练习"}\n```'},
                                "finish_reason": "stop",
                            }
                        ]
                    }
                ),
                event("[DONE]"),
            ]
        )
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=stream
        )

    config = Settings(
        model_provider="fastgpt",
        fastgpt_url="https://model.test/api",
        fastgpt_key="KEY",
        fastgpt_app_id="APP",
    )
    model = PracticeModelClient(config, httpx.MockTransport(handle))
    assert model.generate_json_with_progress(
        [{"role": "user", "content": "生成"}], updates.append
    ) == {"title": "练习"}
    assert calls[0]["stream"] is True and calls[0]["detail"] is False
    assert updates[-1]["received_chars"] > 0
    assert config.timeout == 120


def test_premature_stream_does_not_publish_parseable_partial_json():
    def handle(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Chunks(
                [event({"choices": [{"delta": {"content": '{"title":"partial"}'}}]})]
            ),
        )

    config = Settings(
        model_provider="fastgpt",
        fastgpt_url="https://model.test",
        fastgpt_key="KEY",
        fastgpt_app_id="APP",
    )
    with pytest.raises(ModelOutputError, match="中断"):
        PracticeModelClient(config, httpx.MockTransport(handle)).generate_json(
            [{"role": "user", "content": "生成"}]
        )


def test_stream_error_and_length_finish_are_not_silently_accepted():
    config = Settings(
        model_provider="fastgpt",
        fastgpt_url="https://model.test",
        fastgpt_key="KEY",
        fastgpt_app_id="APP",
    )
    for events in (
        [event({"message": "工作流失败"}, "error")],
        [
            event(
                {"choices": [{"delta": {"content": "{}"}, "finish_reason": "length"}]}
            ),
            event("[DONE]"),
        ],
    ):
        with pytest.raises(ValueError):
            PracticeModelClient(
                config,
                httpx.MockTransport(
                    lambda request: httpx.Response(
                        200,
                        headers={"content-type": "text/event-stream"},
                        stream=Chunks(events),
                    )
                ),
            ).generate_json([{"role": "user", "content": "生成"}])


def test_context_prefers_current_lesson_and_does_not_send_templates_or_transport_metadata():
    from backend.app.timed_practice.context import prepare_source_context

    sources = [
        dict(
            id="template",
            title="限时练模板.docx",
            evidence="模板" * 100,
            locator="slice",
            category="reference",
        )
    ]
    for i in range(18):
        sources.append(
            dict(
                id=str(i),
                title=(
                    "第一章第三节第1课时 氧化还原反应.docx"
                    if i >= 12
                    else "物质的分类.docx"
                ),
                evidence=("本课化合价与电子转移" if i >= 12 else "其他课题资料") * 200,
                category="reference",
                locator="原文位置",
                dataset_id="private-dataset",
                collection_id="private-collection",
                verified=False,
            )
        )
    context, stats = prepare_source_context(
        sources, {"chapter": "第三节 氧化还原反应", "period": "第一课时"}, origin="any"
    )
    assert context[0]["id"] == "12"
    assert "template" not in [s["id"] for s in context]
    assert sum(len(s["evidence"]) for s in context) <= 12000
    assert all("dataset_id" not in s and "collection_id" not in s for s in context)
    assert stats["selected_count"] < len(sources)
    assert sources[0]["id"] == "template"


def test_pipeline_records_stream_progress_context_size_and_failed_stage(tmp_path):
    from backend.app.timed_practice.pipeline import PracticePipeline
    from backend.app.timed_practice.store import PracticeStore
    from backend.app.timed_practice.models import LessonSettings

    store = PracticeStore(tmp_path / "practice.sqlite")
    lesson = store.create_session(LessonSettings().model_dump())
    captured = []

    class Model:
        def generate_json_with_progress(self, messages, callback):
            captured.append(json.loads(messages[1]["content"]))
            callback({"received_chars": 1000, "elapsed_seconds": 125})
            raise ValueError("模拟连接中断")

    sources = [
        dict(
            id="s1",
            title="氧化还原反应",
            category="textbook",
            locator="片段",
            evidence="资料原文",
            verified=False,
        )
    ]
    pipeline = PracticePipeline(
        Settings(data_dir=tmp_path),
        store,
        SimpleNamespace(search=lambda q: sources),
        Model(),
    )
    job = store.create_job(lesson["id"], dict(kind="generation", prompt="生成"))
    pipeline.run(job["id"])
    result = store.get_job(job["id"])
    assert result["status"] == "failed"
    assert result["model_progress"]["received_chars"] == 1000
    assert result["model_context"]["selected_count"] == 1
    assert result["stages"][-1]["status"] == "failed"
    assert "1000" in result["stages"][-1]["label"]
    assert store.get_session(lesson["id"])["sources"] == sources


def transport_settings(**overrides):
    return SimpleNamespace(
        model_provider="fastgpt",
        fastgpt_url="https://model.test",
        fastgpt_key="KEY",
        fastgpt_app_id="APP",
        **overrides,
    )


def test_done_returns_without_waiting_for_provider_connection_to_close():
    class CompletedStream(httpx.SyncByteStream):
        def __iter__(self):
            yield event(
                {"choices": [{"delta": {"content": "{}"}, "finish_reason": "stop"}]}
            )
            yield event("[DONE]")
            raise httpx.ReadTimeout("provider kept connection open")

    model = PracticeModelClient(
        transport_settings(),
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=CompletedStream(),
            )
        ),
    )
    assert model.generate_json([]) == {}


def test_non_stream_fallback_rejects_truncated_json_even_if_parseable():
    model = PracticeModelClient(
        transport_settings(),
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {"content": '{"title":"partial"}'},
                            "finish_reason": "length",
                        }
                    ]
                },
            )
        ),
    )
    with pytest.raises(ModelOutputError, match="截断"):
        model.generate_json([])


def test_total_deadline_interrupts_blocked_stream_read():
    import threading
    import time

    closed = threading.Event()

    class StalledStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b": keepalive\n\n"
            closed.wait(2)
            raise httpx.ReadError("stream closed")

        def close(self):
            closed.set()

    model = PracticeModelClient(
        transport_settings(model_read_timeout=3, model_total_timeout=0.1),
        httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=StalledStream(),
            )
        ),
    )
    started = time.monotonic()
    with pytest.raises(ValueError, match="超过0.1秒"):
        model.generate_json([])
    assert time.monotonic() - started < 1
    assert closed.is_set()


def test_total_deadline_wakes_real_socket_waiting_for_unfinished_line():
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    release = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b": unfinished heartbeat")
            self.wfile.flush()
            release.wait(2)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    config = transport_settings(model_read_timeout=3, model_total_timeout=0.2)
    config.fastgpt_url = f"http://127.0.0.1:{server.server_port}"
    started = time.monotonic()
    try:
        with pytest.raises(ValueError, match="超过0.2秒"):
            PracticeModelClient(config).generate_json([])
        assert time.monotonic() - started < 1
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        worker.join()

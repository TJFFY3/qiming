import json
import threading
import time

import httpx
import pytest

from backend.app.config import Settings
from backend.app.courseware.model_client import (
    CoursewareModelClient,
    CoursewareModelOutputError,
)


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def event(data, name="answer"):
    prefix = f"event: {name}\n" if name else ""
    body = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return (prefix + "data: " + body + "\n\n").encode()


def fastgpt_settings(**overrides):
    timeout_overrides = {
        key: overrides.pop(key)
        for key in ("model_read_timeout", "model_total_timeout")
        if key in overrides
    }
    values = dict(
        model_provider="fastgpt",
        fastgpt_url="https://model.test/api",
        fastgpt_key="KEY",
        fastgpt_app_id="APP",
        **overrides,
    )
    settings = Settings(**values)
    for key, value in timeout_overrides.items():
        setattr(settings, key, value)
    return settings


def test_courseware_stream_parses_answer_deltas_and_uses_independent_timeout():
    calls = []

    def handle(request):
        calls.append(json.loads(request.content))
        assert request.extensions["timeout"]["read"] > 120
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Chunks(
                [
                    b": heartbeat\n\n",
                    event({"choices": [{"delta": {"reasoning_content": "推理"}}]}),
                    event(
                        {"choices": [{"delta": {"content": "不要混入"}}]},
                        "flowNodeStatus",
                    ),
                    event({"choices": [{"delta": {"content": '{"title":'}}]}),
                    event(
                        {
                            "choices": [
                                {
                                    "delta": {"content": '"课件"}'},
                                    "finish_reason": "stop",
                                }
                            ]
                        }
                    ),
                    event("[DONE]"),
                ]
            ),
        )

    result = CoursewareModelClient(
        fastgpt_settings(), httpx.MockTransport(handle)
    ).generate_json([{"role": "user", "content": "生成课件"}])

    assert result == {"title": "课件"}
    assert calls[0]["stream"] is True
    assert calls[0]["detail"] is False


def test_courseware_stream_rejects_incomplete_response():
    def handle(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=Chunks(
                [event({"choices": [{"delta": {"content": '{"title":"部分"}'}}]})]
            ),
        )

    with pytest.raises(CoursewareModelOutputError, match="中断"):
        CoursewareModelClient(
            fastgpt_settings(), httpx.MockTransport(handle)
        ).generate_json([])


def test_courseware_non_stream_fallback_rejects_truncated_json():
    def handle(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"content": '{"title":"部分"}'},
                        "finish_reason": "length",
                    }
                ]
            },
        )

    with pytest.raises(CoursewareModelOutputError, match="截断"):
        CoursewareModelClient(
            fastgpt_settings(), httpx.MockTransport(handle)
        ).generate_json([])


def test_courseware_total_deadline_interrupts_blocked_stream_read():
    closed = threading.Event()

    class StalledStream(httpx.SyncByteStream):
        def __iter__(self):
            yield b": keepalive\n\n"
            closed.wait(2)
            raise httpx.ReadError("stream closed")

        def close(self):
            closed.set()

    settings = fastgpt_settings(model_read_timeout=3, model_total_timeout=0.1)
    started = time.monotonic()
    with pytest.raises(ValueError, match="超过0.1秒"):
        CoursewareModelClient(
            settings,
            httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/event-stream"},
                    stream=StalledStream(),
                )
            ),
        ).generate_json([])
    assert time.monotonic() - started < 1
    assert closed.is_set()

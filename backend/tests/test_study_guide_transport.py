"""Guide model transport: streaming, independent timeouts and bounded waiting."""
import json
import threading
import time

import httpx
import pytest

from backend.app.config import Settings
from backend.app.study_guide.llm.client import ModelClient, ModelServiceError


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks

    def __iter__(self):
        yield from self.chunks


def event(value, name="answer"):
    data = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return (f"event: {name}\ndata: {data}\n\n").encode()


def settings(**overrides):
    config = Settings(model_provider="fastgpt", fastgpt_url="https://model.test/api",
                      fastgpt_app_id="APP", fastgpt_key="KEY", timeout=120)
    for key, value in overrides.items():
        setattr(config, key, value)
    return config


def test_streaming_uses_independent_model_timeout_and_only_answer_content():
    def handle(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert request.extensions["timeout"]["read"] == 300
        assert request.headers["accept"] == "text/event-stream"
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            stream=Chunks([
                b": heartbeat\n\n",
                event({"choices": [{"delta": {"content": "忽略状态"}, "finish_reason": "stop"}]}, "flowNodeStatus"),
                event({"choices": [{"delta": {"reasoning_content": "思考"}}]}),
                event({"choices": [{"delta": {"content": '{"outline":'}}]}),
                event({"choices": [{"delta": {"content": '{}}'}, "finish_reason": "stop"}]}),
                event("[DONE]"),
            ]))
    assert ModelClient(settings(), httpx.MockTransport(handle)).generate_json([]) == {"outline": {}}


def test_openai_stream_and_model_timeout_overrides():
    config = settings(model_provider="openai", model_url="https://model.test/v1",
                      model="test", model_key="KEY", model_read_timeout=240,
                      model_total_timeout=500)
    def handle(request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        assert payload["response_format"] == {"type": "json_object"}
        assert request.extensions["timeout"]["read"] == 240
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"outline":{}}'}}]})
    assert ModelClient(config, httpx.MockTransport(handle)).generate_json([]) == {"outline": {}}


def test_partial_stream_is_service_error_not_repairable_json():
    def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            stream=Chunks([event({"choices": [{"delta": {"content": '{"outline":{}}'}}]})]))
    with pytest.raises(ModelServiceError, match="中断"):
        ModelClient(settings(), httpx.MockTransport(handle)).generate_json([])


def test_stream_length_finish_retains_output_for_existing_repair():
    from backend.app.study_guide.llm.client import ModelOutputError
    def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            stream=Chunks([event({"choices": [{"delta": {"content": '{"outline":{}'}, "finish_reason": "length"}]})]))
    with pytest.raises(ModelOutputError, match="截断") as error:
        ModelClient(settings(), httpx.MockTransport(handle)).generate_json([])
    assert error.value.response_text == '{"outline":{}'


@pytest.mark.parametrize("partial", [False, True])
def test_read_timeout_reports_phase_and_received_characters(partial):
    class TimeoutStream(httpx.SyncByteStream):
        def __iter__(self):
            if partial:
                yield event({"choices": [{"delta": {"content": '{"outline":'}}]})
            raise httpx.ReadTimeout("test")
    def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=TimeoutStream())
    with pytest.raises(ModelServiceError) as error:
        ModelClient(settings(model_read_timeout=250), httpx.MockTransport(handle)).generate_json([])
    assert "250秒" in str(error.value)
    assert ("已收到11字" if partial else "首段") in str(error.value)


def test_total_deadline_interrupts_blocked_stream_read():
    closed = threading.Event()
    class Stalled(httpx.SyncByteStream):
        def __iter__(self):
            yield b": heartbeat\n\n"
            closed.wait(2)
            raise httpx.ReadError("closed")
        def close(self):
            closed.set()
    def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stalled())
    start = time.monotonic()
    with pytest.raises(ModelServiceError, match="超过0.1秒"):
        ModelClient(settings(model_read_timeout=3, model_total_timeout=.1),
                    httpx.MockTransport(handle)).generate_json([])
    assert time.monotonic() - start < 1
    assert closed.is_set()


def test_workflow_error_is_service_failure():
    def handle(request):
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            stream=Chunks([event({"message": "private details"}, "error")]))
    with pytest.raises(ModelServiceError, match="工作流"):
        ModelClient(settings(), httpx.MockTransport(handle)).generate_json([])

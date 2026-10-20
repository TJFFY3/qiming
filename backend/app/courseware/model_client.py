"""Streaming model adapter for the independent courseware Agent."""

import json
import socket
import threading
import time
from contextlib import contextmanager

import httpx


class CoursewareModelOutputError(ValueError):
    """The provider finished, but the response cannot be used as courseware JSON."""


@contextmanager
def response_deadline(response, started, seconds):
    """Interrupt a blocked stream read when the total generation budget expires."""
    expired = threading.Event()

    def interrupt():
        expired.set()
        # Closing alone may not wake a concurrent socket recv.
        stream = response.extensions.get("network_stream")
        try:
            connection = stream.get_extra_info("socket") if stream else None
            if connection:
                connection.shutdown(socket.SHUT_RDWR)
        except (OSError, AttributeError):
            pass
        try:
            response.close()
        except (OSError, RuntimeError, httpx.HTTPError):
            pass

    timer = threading.Timer(max(0, seconds - (time.monotonic() - started)), interrupt)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()
        if expired.is_set():
            raise ValueError(
                f"本次课件生成超过{seconds:g}秒，已停止；请稍后重试或减少课件页数"
            ) from None


class CoursewareModelClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    @staticmethod
    def _parse_json(text):
        text = text.strip()
        if text.startswith("```"):
            try:
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            except IndexError:
                raise CoursewareModelOutputError(
                    "课件模型返回不完整的 JSON 代码块"
                ) from None
        try:
            result = json.loads(
                text,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("非有限数值")
                ),
            )
        except (ValueError, TypeError):
            raise CoursewareModelOutputError(
                "课件模型返回无效 JSON 或内容不完整"
            ) from None
        if not isinstance(result, dict):
            raise CoursewareModelOutputError("课件模型响应必须为 JSON 对象")
        return result

    def _request(self, messages):
        s = self.settings
        if s.model_provider == "fastgpt":
            if not all((s.fastgpt_app_id, s.fastgpt_url, s.fastgpt_key)):
                raise ValueError("请配置互动课件的 FastGPT 应用连接")
            base = s.fastgpt_url.rstrip("/")
            if not base.endswith("/api"):
                base += "/api"
            url, key = base + "/v1/chat/completions", s.fastgpt_key
            payload = dict(
                appId=s.fastgpt_app_id,
                stream=True,
                detail=False,
                messages=[
                    dict(
                        role="user",
                        content="执行独立互动课件任务，只输出 JSON。\n\n"
                        + "\n\n".join(
                            f"[{m['role']}]\n{m['content']}" for m in messages
                        ),
                    )
                ],
            )
        else:
            if not all((s.model_url, s.model_key, s.model)):
                raise ValueError("请配置互动课件生成模型连接")
            url, key = s.model_url.rstrip("/") + "/chat/completions", s.model_key
            payload = dict(
                model=s.model,
                messages=messages,
                stream=True,
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=12000,
            )
        return url, key, payload

    def generate_json(self, messages):
        url, key, payload = self._request(messages)
        s = self.settings
        read_timeout = float(getattr(s, "model_read_timeout", 300))
        total_timeout = float(getattr(s, "model_total_timeout", 600))
        timeout = httpx.Timeout(
            connect=min(15, total_timeout),
            read=min(read_timeout, total_timeout),
            write=min(30, total_timeout),
            pool=min(15, total_timeout),
        )
        started = time.monotonic()
        received = 0
        text = ""

        try:
            with httpx.Client(timeout=timeout, transport=self.transport) as client:
                with (
                    client.stream(
                        "POST",
                        url,
                        headers={
                            "Authorization": "Bearer " + key,
                            "Accept": "text/event-stream",
                        },
                        json=payload,
                    ) as response,
                    response_deadline(response, started, total_timeout),
                ):
                    response.raise_for_status()
                    if "text/event-stream" not in response.headers.get(
                        "content-type", ""
                    ).lower():
                        body = json.loads(response.read())
                        if body.get("code") == 513001 or body.get(
                            "statusText"
                        ) == "modelUnConfigured":
                            raise ValueError("互动课件生成应用未配置模型")
                        try:
                            choice = body["choices"][0]
                            text = choice["message"]["content"]
                        except (KeyError, TypeError, IndexError):
                            raise CoursewareModelOutputError(
                                "课件模型响应结构不正确"
                            ) from None
                        if choice.get("finish_reason") == "length":
                            raise CoursewareModelOutputError(
                                "课件模型输出被截断，请减少课件页数或提高应用输出上限"
                            )
                        if not isinstance(text, str):
                            raise CoursewareModelOutputError(
                                "课件模型正文必须为文字"
                            )
                        received = len(text)
                    else:
                        parts = []
                        completed = False
                        done = False
                        event_name = ""
                        data = []

                        def consume():
                            nonlocal completed, done, received
                            if not data:
                                return
                            raw = "\n".join(data)
                            if raw.strip() == "[DONE]":
                                done = True
                                completed = True
                                return
                            try:
                                item = json.loads(raw)
                            except ValueError:
                                raise CoursewareModelOutputError(
                                    "课件模型流式响应包含无效 JSON 事件"
                                ) from None
                            if event_name == "error":
                                raise ValueError(
                                    "FastGPT 工作流执行失败，请检查互动课件应用配置"
                                )
                            # FastGPT emits reasoning and workflow status events;
                            # only answer events may contribute to the JSON body.
                            if event_name not in ("", "answer", "fastAnswer"):
                                return
                            if not isinstance(item, dict):
                                return
                            if item.get("error") or item.get("code") not in (
                                None,
                                0,
                                200,
                            ):
                                raise ValueError(
                                    "模型服务返回执行错误，请检查互动课件应用"
                                )
                            for choice in item.get("choices", []):
                                delta = choice.get("delta") or {}
                                piece = delta.get("content", "")
                                if piece:
                                    if not isinstance(piece, str):
                                        raise CoursewareModelOutputError(
                                            "课件模型流式正文格式不正确"
                                        )
                                    parts.append(piece)
                                    received += len(piece)
                                    if received > 512000:
                                        raise CoursewareModelOutputError(
                                            "课件模型输出过长，请减少课件页数或内容"
                                        )
                                if choice.get("finish_reason"):
                                    if choice["finish_reason"] == "length":
                                        raise CoursewareModelOutputError(
                                            "课件模型输出被截断，请减少课件页数或提高应用输出上限"
                                        )
                                    if choice["finish_reason"] == "stop":
                                        completed = True

                        for line in response.iter_lines():
                            if not line:
                                consume()
                                event_name = ""
                                data = []
                                if done or completed:
                                    break
                            elif line.startswith("event:"):
                                event_name = line[6:].strip()
                            elif line.startswith("data:"):
                                data.append(line[5:].lstrip())
                        consume()
                        if not completed:
                            raise CoursewareModelOutputError(
                                "课件模型流式连接中断，未收到完整结束标记，请重试"
                            )
                        text = "".join(parts)
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"课件模型调用失败（HTTP {exc.response.status_code}），请检查服务与权限"
            ) from None
        except httpx.TimeoutException:
            phase = "等待首段内容" if not received else f"接收内容（已收到{received}字）"
            raise ValueError(
                f"课件模型在{phase}时超时：连续{read_timeout:g}秒没有返回数据，请稍后重试"
            ) from None
        except httpx.HTTPError:
            raise ValueError("课件模型连接中断，请检查服务后重试") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CoursewareModelOutputError("课件模型返回无效 JSON 响应") from None

        return self._parse_json(text)

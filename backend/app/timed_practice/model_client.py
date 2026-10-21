"""Practice-only streaming transport. A completed response is required before JSON parsing."""

import json
import socket
import threading
import time
from contextlib import contextmanager

import httpx


class ModelOutputError(ValueError):
    """A completed model response could not be parsed; eligible for bounded repair."""

    def __init__(self, message, response_text=""):
        super().__init__(message)
        self.response_text = response_text


@contextmanager
def response_deadline(response, started, seconds):
    """Interrupt a blocked body read when the practice generation budget expires."""
    expired = threading.Event()

    def interrupt():
        expired.set()
        # Closing alone need not wake a concurrent recv; shutdown wakes it first.
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
                f"本次模型生成超过{seconds:g}秒，已停止；请稍后重试或减少题量"
            ) from None


class PracticeModelClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def generate_json(self, messages):
        return self.generate_json_with_progress(messages, None)

    def generate_json_with_progress(self, messages, on_progress):
        s = self.settings
        if s.model_provider == "fastgpt":
            if not s.fastgpt_app_id or not s.fastgpt_url or not s.fastgpt_key:
                raise ValueError(
                    "FastGPT 生成应用未配置，请填写限时练习应用、地址和密钥"
                )
            base = s.fastgpt_url.rstrip("/")
            if not base.endswith("/api"):
                base += "/api"
            url = base + "/v1/chat/completions"
            key = s.fastgpt_key
            payload = dict(
                appId=s.fastgpt_app_id,
                stream=True,
                detail=False,
                messages=[
                    dict(
                        role="user",
                        content="执行独立限时练习任务，只输出完整JSON；解析清楚简洁，不重复题干。\n\n"
                        + "\n\n".join(
                            f"[{m['role']}]\n{m['content']}" for m in messages
                        ),
                    )
                ],
            )
        else:
            if not s.model_url or not s.model_key or not s.model:
                raise ValueError("请配置限时练习模型的地址、密钥和模型名")
            url = s.model_url.rstrip("/") + "/chat/completions"
            key = s.model_key
            payload = dict(
                model=s.model,
                messages=messages,
                stream=True,
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=12000,
            )
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
        last_notify = -10
        last_count = -1

        def progress(force=False):
            nonlocal last_notify, last_count
            elapsed = time.monotonic() - started
            if elapsed > total_timeout:
                raise ValueError(
                    f"本次模型生成超过{total_timeout:g}秒，已停止；请稍后重试或减少题量"
                )
            if on_progress and (
                force or elapsed - last_notify >= 1 or received - last_count >= 1000
            ):
                on_progress(dict(received_chars=received, elapsed_seconds=int(elapsed)))
                last_notify = elapsed
                last_count = received

        progress(True)
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
                    if (
                        "text/event-stream"
                        not in response.headers.get("content-type", "").lower()
                    ):
                        body = json.loads(response.read())
                        if (
                            body.get("code") == 513001
                            or body.get("statusText") == "modelUnConfigured"
                        ):
                            raise ValueError("FastGPT 限时练习应用未完成模型配置")
                        try:
                            choice = body["choices"][0]
                            text = choice["message"]["content"]
                        except (KeyError, TypeError, IndexError):
                            raise ModelOutputError(
                                "限时练习模型响应结构不正确"
                            ) from None
                        if choice.get("finish_reason") == "length":
                            raise ModelOutputError(
                                "模型输出被截断，请提高最大输出长度或减少题量",
                                response_text=text if isinstance(text, str) else "",
                            )
                        if not isinstance(text, str):
                            raise ModelOutputError("限时练习模型正文必须为文字")
                        received = len(text)
                        progress(True)
                    else:
                        parts = []
                        completed = False
                        done = False
                        finish = None
                        event_name = ""
                        data = []

                        def consume():
                            nonlocal completed, done, finish, received
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
                                raise ModelOutputError(
                                    "模型流式响应包含无效JSON事件",
                                    response_text="".join(parts),
                                ) from None
                            if event_name == "error":
                                raise ValueError(
                                    "FastGPT 工作流执行失败，请检查限时练习应用配置"
                                )
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
                                    "模型服务返回执行错误，请检查限时练习应用"
                                )
                            for choice in item.get("choices", []):
                                delta = choice.get("delta") or {}
                                piece = delta.get("content", "")
                                if piece:
                                    if not isinstance(piece, str):
                                        raise ModelOutputError("模型流式正文格式不正确")
                                    parts.append(piece)
                                    received += len(piece)
                                    if received > 256000:
                                        raise ModelOutputError(
                                            "模型输出过长，请缩短试题解析",
                                            response_text="".join(parts),
                                        )
                                if choice.get("finish_reason"):
                                    finish = choice["finish_reason"]
                                    if finish == "length":
                                        raise ModelOutputError(
                                            "模型输出被截断，请提高限时练习应用的最大输出长度或减少题量",
                                            response_text="".join(parts),
                                        )
                                    if finish == "stop":
                                        completed = True

                        for line in response.iter_lines():
                            progress()
                            if not line:
                                consume()
                                event_name = ""
                                data = []
                                if done:
                                    break
                            elif line.startswith("event:"):
                                event_name = line[6:].strip()
                            elif line.startswith("data:"):
                                data.append(line[5:].lstrip())
                        consume()
                        if not completed:
                            raise ModelOutputError(
                                "模型流式连接中断，未收到完整结束标记，请重试",
                                response_text="".join(parts),
                            )
                        text = "".join(parts)
                        progress(True)
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"模型调用失败（HTTP {exc.response.status_code}），请检查限时练习模型服务与权限"
            ) from None
        except httpx.TimeoutException:
            phase = (
                "等待首段内容" if not received else f"接收内容（已收到{received}字）"
            )
            raise ValueError(
                f"限时练习模型在{phase}时超时：连续{read_timeout:g}秒没有返回数据，请稍后重试"
            ) from None
        except httpx.HTTPError:
            raise ValueError("限时练习模型连接中断，请检查模型服务后重试") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ModelOutputError("限时练习模型返回无效JSON响应") from None
        text = text.strip()
        if text.startswith("```"):
            try:
                text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            except IndexError:
                raise ModelOutputError("模型返回不完整的JSON代码块") from None
        try:
            result = json.loads(
                text,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("非有限数值")
                ),
            )
            if not isinstance(result, dict):
                raise ValueError("必须为对象")
            return result
        except json.JSONDecodeError as exc:
            raise ModelOutputError(
                f"限时练习模型返回无效JSON（第{exc.lineno}行第{exc.colno}列，收到{len(text)}字）：{exc.msg}",
                response_text=text,
            ) from None
        except (ValueError, TypeError):
            raise ModelOutputError(
                "限时练习模型返回无效JSON或内容不完整", response_text=text
            ) from None

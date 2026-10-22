"""【模型调用·导学案】发送模型 HTTP 请求、接收完整响应并解析 JSON；业务修复轮次由 pipeline 控制。"""

import json
import socket
import threading
import time
from contextlib import contextmanager
import httpx


class ModelServiceError(ValueError):
    """Connection, configuration or provider errors cannot be repaired as content."""


class ModelOutputError(ValueError):
    def __init__(self, message, response_text=""):
        super().__init__(message)
        self.response_text = response_text


@contextmanager
def response_deadline(response, started, seconds):
    """Close a stalled response even if the server keeps sending heartbeats."""
    expired = threading.Event()

    def interrupt():
        expired.set()
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
            raise ModelServiceError(f"本次导学案模型调用超过{seconds:g}秒，已停止，请稍后重试") from None


class ModelClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def _request(self, messages):
        s = self.settings
        if s.model_provider == "fastgpt":
            if not s.fastgpt_app_id or not s.fastgpt_url or not s.fastgpt_key:
                raise ModelServiceError(
                    "FastGPT 生成应用未配置，请填写 fastgpt_app_id、地址和密钥"
                )
            base = s.fastgpt_url.rstrip("/")
            if not base.endswith("/api"):
                base += "/api"
            url = base + "/v1/chat/completions"
            key = s.fastgpt_key
            # FastGPT runs an application workflow, so model/temperature are workflow settings.
            # Put the complete constrained task in a user message: workflow system prompts may ignore API system roles.
            content = (
                "请执行下面的导学案内容任务，严格遵守结构要求，只输出 JSON。\n\n"
                + "\n\n".join(f"[{m['role']}]\n{m['content']}" for m in messages)
            )
            payload = {
                "appId": s.fastgpt_app_id,
                "stream": True,
                "detail": False,
                "messages": [{"role": "user", "content": content}],
            }
        else:
            if not s.model_url or not s.model_key or not s.model:
                raise ModelServiceError(
                    "模型未配置，请编辑 backend/app/config.py 中的 model_url、model_key、model"
                )
            url = s.model_url.rstrip("/") + "/chat/completions"
            key = s.model_key
            payload = {
                "model": s.model,
                "stream": True,
                "messages": messages,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "max_tokens": 12000,
            }
        return url, key, payload

    # 【模型调用入口】传输与 JSON 解析；教学语义校验交给 pipeline。
    def generate_json(self, messages: list[dict]) -> dict:
        url, key, payload = self._request(messages)
        read_timeout = float(getattr(self.settings, "model_read_timeout", 300))
        total_timeout = float(getattr(self.settings, "model_total_timeout", 600))
        if read_timeout <= 0 or total_timeout <= 0:
            raise ModelServiceError("模型等待时间和总时限必须大于 0")
        timeout = httpx.Timeout(
            connect=min(15, total_timeout), read=min(read_timeout, total_timeout),
            write=min(30, total_timeout), pool=min(15, total_timeout),
        )
        started = time.monotonic()
        parts = []
        received = 0
        try:
            with httpx.Client(timeout=timeout, transport=self.transport) as client:
                with client.stream(
                    "POST", url,
                    headers={"Authorization": "Bearer " + key, "Accept": "text/event-stream"},
                    json=payload,
                ) as response, response_deadline(response, started, total_timeout):
                    if "text/event-stream" not in response.headers.get("content-type", "").lower():
                        # Some compatible providers return a regular JSON envelope even with stream=true.
                        try:
                            body = json.loads(response.read())
                        except (ValueError, UnicodeDecodeError):
                            response.raise_for_status()
                            raise ModelServiceError("模型服务返回非 JSON 响应") from None
                        if isinstance(body, dict) and (
                            body.get("code") == 513001 or body.get("statusText") == "modelUnConfigured"
                        ):
                            raise ModelServiceError("FastGPT 生成应用未完成模型配置（513001 / modelUnConfigured）")
                        response.raise_for_status()
                        try:
                            choice = body["choices"][0]
                            text = choice["message"]["content"]
                        except (KeyError, TypeError, IndexError):
                            raise ModelServiceError("模型服务响应缺少 choices[0].message.content") from None
                        if not isinstance(text, str):
                            raise ModelOutputError("模型正文必须为 JSON 文字")
                        if choice.get("finish_reason") == "length":
                            raise ModelOutputError("模型输出被截断，请提高模型或 FastGPT 应用的输出上限，或缩小本课内容范围", text)
                    else:
                        response.raise_for_status()
                        completed = done = False
                        event_name = ""
                        data = []

                        def consume():
                            nonlocal completed, done, received
                            if not data:
                                return
                            raw = "\n".join(data)
                            if raw.strip() == "[DONE]":
                                completed = done = True
                                return
                            if event_name == "error":
                                raise ModelServiceError("FastGPT 工作流执行失败，请检查生成应用配置")
                            # Reasoning, node status and intermediate node stops are not answer content.
                            if event_name not in ("", "answer", "fastAnswer"):
                                return
                            try:
                                item = json.loads(raw)
                            except ValueError:
                                raise ModelServiceError("模型流式响应包含无效 JSON 事件，请重试") from None
                            if not isinstance(item, dict):
                                raise ModelServiceError("模型流式响应格式不正确")
                            if item.get("error") or item.get("code") not in (None, 0, 200):
                                raise ModelServiceError("模型服务返回执行错误，请检查生成应用配置")
                            choices = item.get("choices", [])
                            if not isinstance(choices, list):
                                raise ModelServiceError("模型流式响应 choices 格式不正确")
                            for choice in choices:
                                if not isinstance(choice, dict):
                                    raise ModelServiceError("模型流式响应 choice 格式不正确")
                                delta = choice.get("delta") or {}
                                if not isinstance(delta, dict):
                                    raise ModelServiceError("模型流式响应 delta 格式不正确")
                                piece = delta.get("content", "")
                                if piece:
                                    if not isinstance(piece, str):
                                        raise ModelServiceError("模型流式正文必须为文字")
                                    parts.append(piece)
                                    received += len(piece)
                                    if received > 512000:
                                        raise ModelServiceError("模型输出过长，请缩小本课内容范围")
                                if choice.get("finish_reason") == "length":
                                    raise ModelOutputError("模型输出被截断，请提高模型或 FastGPT 应用的输出上限，或缩小本课内容范围", "".join(parts))
                                if choice.get("finish_reason") == "stop":
                                    completed = True

                        for line in response.iter_lines():
                            if not line:
                                consume()
                                event_name, data = "", []
                                if done:
                                    break
                            elif line.startswith("event:"):
                                event_name = line[6:].strip()
                            elif line.startswith("data:"):
                                data.append(line[5:].lstrip())
                        consume()
                        if not completed:
                            raise ModelServiceError(f"模型流式连接中断，未收到完整结束标记（已收到{received}字），请重试")
                        text = "".join(parts)
        except httpx.HTTPStatusError as exc:
            raise ModelServiceError(
                f"模型调用失败（HTTP {exc.response.status_code}），请检查模型或 FastGPT 应用配置与权限"
            ) from None
        except httpx.TimeoutException:
            phase = "等待首段内容" if not received else f"接收内容（已收到{received}字）"
            raise ModelServiceError(
                f"模型在{phase}时超时：连续{min(read_timeout, total_timeout):g}秒未收到数据，请重试"
            ) from None
        except httpx.HTTPError:
            raise ModelServiceError(f"模型连接中断（已收到{received}字），请检查服务后重试") from None
        return self._parse_json(text)

    @staticmethod
    def _parse_json(text):
        original = text
        text = text.strip()
        if text.startswith("```"):
            if "\n" not in text or not text.endswith("```"):
                raise ModelOutputError("模型返回不完整的 JSON 代码块", original)
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            value = json.loads(
                text,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("JSON 包含非有限数值")
                ),
            )
        except json.JSONDecodeError as exc:
            raise ModelOutputError(
                f"模型返回无效 JSON（第{exc.lineno}行第{exc.colno}列，收到{len(text)}字）：{exc.msg}",
                original,
            ) from None
        except ValueError:
            raise ModelOutputError("模型 JSON 包含非有限数值", original) from None
        if not isinstance(value, dict):
            raise ModelOutputError("模型 JSON 必须为对象", original)
        return value

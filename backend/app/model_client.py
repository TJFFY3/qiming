import json
import httpx


class ModelServiceError(ValueError):
    """Connection, configuration or provider errors cannot be repaired as content."""


class ModelOutputError(ValueError):
    def __init__(self, message, response_text=""):
        super().__init__(message)
        self.response_text = response_text


class ModelClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def generate_json(self, messages: list[dict]) -> dict:
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
                "stream": False,
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
                "messages": messages,
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
                "max_tokens": 12000,
            }
        try:
            with httpx.Client(timeout=s.timeout, transport=self.transport) as client:
                response = client.post(
                    url, headers={"Authorization": "Bearer " + key}, json=payload
                )
                try:
                    body = response.json()
                except ValueError:
                    response.raise_for_status()
                    raise ModelServiceError("模型服务返回非 JSON 响应")
                if isinstance(body, dict) and (
                    body.get("code") == 513001
                    or body.get("statusText") == "modelUnConfigured"
                ):
                    raise RuntimeError(
                        "FastGPT 生成应用未完成模型配置（513001 / modelUnConfigured）"
                    )
                response.raise_for_status()
                try:
                    choice = body["choices"][0]
                    text = choice["message"]["content"]
                except (KeyError, TypeError, IndexError):
                    raise ModelServiceError("模型服务响应缺少 choices[0].message.content") from None
                if not isinstance(text, str):
                    raise ModelOutputError("模型正文必须为 JSON 文字")
                if choice.get("finish_reason") == "length":
                    raise ModelOutputError(
                        "模型输出被截断，请提高模型或 FastGPT 应用的输出上限，或缩小本课内容范围",
                        response_text=text,
                    )
                return self._parse_json(text)
        except RuntimeError as exc:
            raise ModelServiceError(str(exc)) from None
        except httpx.HTTPStatusError as exc:
            raise ModelServiceError(
                f"模型调用失败（HTTP {exc.response.status_code}），请检查模型或 FastGPT 应用配置与权限"
            ) from None
        except httpx.TimeoutException:
            raise ModelServiceError("模型响应超时，请重试") from None
        except httpx.HTTPError:
            raise ModelServiceError("无法连接模型服务，请检查服务地址") from None

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

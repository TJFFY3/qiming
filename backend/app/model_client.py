import json
import httpx


class ModelClient:
    def __init__(self, settings, transport=None):
        self.settings, self.transport = settings, transport

    def generate_json(self, messages: list[dict]) -> dict:
        s = self.settings
        if not s.model_url or not s.model_key or not s.model:
            raise ValueError('模型未配置，请编辑 backend/app/config.py 中的 model_url、model_key、model')
        try:
            with httpx.Client(timeout=s.timeout, transport=self.transport) as client:
                response = client.post(s.model_url.rstrip('/') + '/chat/completions', headers={'Authorization':'Bearer '+s.model_key}, json={'model':s.model, 'messages':messages, 'temperature':0.3, 'response_format':{'type':'json_object'}, 'max_tokens':12000})
                response.raise_for_status()
                text = response.json()['choices'][0]['message']['content']
                if text.startswith('```'):
                    text = text.strip().split('\n',1)[1].rsplit('```',1)[0]
                value = json.loads(text, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('JSON 包含非有限数值')))
                if not isinstance(value, dict):
                    raise ValueError('模型 JSON 必须为对象')
                return value
        except httpx.HTTPStatusError as exc:
            raise ValueError(f'模型调用失败（HTTP {exc.response.status_code}），请检查模型配置与权限') from None
        except httpx.TimeoutException:
            raise ValueError('模型响应超时，请重试') from None
        except httpx.HTTPError:
            raise ValueError('无法连接模型服务，请检查服务地址') from None
        except (ValueError, KeyError, TypeError, IndexError, AttributeError):
            raise ValueError('模型返回无效 JSON 或响应格式不正确') from None

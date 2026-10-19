"""复制为 config.py，直接修改以下代码配置；该文件只由服务端读取。"""
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

@dataclass
class Settings:
    fastgpt_url: str = ''  # 例如 https://fastgpt.example.com
    fastgpt_key: str = ''
    datasets: list[dict] = field(default_factory=lambda: [
        # {'id': '真实知识库ID', 'category': 'textbook', 'name': '人教版教材'}
    ])
    model_url: str = ''  # OpenAI 兼容服务，例如 https://model.example.com/v1
    model_key: str = ''
    model: str = ''
    search_mode: str = 'mixedRecall'
    similarity: float = 0.2
    search_limit: int = 6000
    using_rerank: bool = False
    timeout: float = 120
    data_dir: Path = ROOT / 'data'

    def missing(self) -> list[str]:
        return [name for name in ('fastgpt_url', 'fastgpt_key', 'datasets', 'model_url', 'model_key', 'model') if not getattr(self, name)]

    def redact(self, value: str) -> str:
        for secret in (self.fastgpt_key, self.model_key):
            if secret:
                value = value.replace(secret, '[已隐藏]')
        return value

settings = Settings()

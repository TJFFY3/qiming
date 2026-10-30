"""复制为 config.py，直接修改以下代码配置；该文件只由服务端读取。"""

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Settings:
    fastgpt_url: str = ""  # 例如 https://fastgpt.example.com
    fastgpt_key: str = ""
    datasets: list[dict] = field(
        default_factory=lambda: [
            # {'id': '真实知识库ID', 'category': 'textbook', 'name': '人教版教材'}
        ]
    )
    model_provider: str = "openai"  # openai 或 fastgpt
    fastgpt_app_id: str = ""
    model_url: str = ""  # OpenAI 兼容服务，例如 https://model.example.com/v1
    model_key: str = ""
    model: str = ""
    search_mode: str = "mixedRecall"
    similarity: float = 0.2
    search_limit: int = 6000
    using_rerank: bool = False
    timeout: float = 120  # 检索等普通请求超时
    model_read_timeout: float = 300  # 导学案模型连续无数据等待上限
    model_total_timeout: float = 600  # 导学案单次模型调用总时限
    data_dir: Path = ROOT / "data"

    def missing(self) -> list[str]:
        fields = ["fastgpt_url", "fastgpt_key", "datasets"] + (
            ["fastgpt_app_id"]
            if self.model_provider == "fastgpt"
            else ["model_url", "model_key", "model"]
        )
        return [name for name in fields if not getattr(self, name)]

    def redact(self, value: str) -> str:
        for secret in (self.fastgpt_key, self.model_key):
            if secret:
                value = value.replace(secret, "[已隐藏]")
        return value


settings = Settings(
    fastgpt_url="https://cloud.fastgpt.cn/api",
    fastgpt_key="fastgpt-fxME2xsve6FXRGRUIif67BdtHW9k4Tj4EVSCTfke26ug8STqSQKSGnFZH",
    datasets=[
        {
            "id": "6ad1e71de8c9ba1dd141b306",
            "category": "reference",
            "name": "高中化学教学三件套智能生成与教学应用验证",
            "type": "folder",
        }
    ],
    model_provider="fastgpt",
    fastgpt_app_id="6ad6041baed8188220b2e36c",
)

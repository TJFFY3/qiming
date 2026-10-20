"""容器内的 config.py：凭据全部来自环境变量，仓库中的 config.example.py 保持原样。

变量（都可不填，不填时生成/检索会提示未配置）：
  FASTGPT_URL / FASTGPT_KEY / FASTGPT_APP_ID / FASTGPT_DATASETS(JSON 数组)
  MODEL_PROVIDER(openai|fastgpt) / MODEL_URL / MODEL_KEY / MODEL_NAME
  DATA_DIR（默认 /app/data，容器内挂持久卷的路径）
"""

import json
import os
from pathlib import Path

from .config_defaults import ROOT, Settings


def _text(name, default=""):
    return os.environ.get(name, "").strip() or default


def _datasets():
    raw = _text("FASTGPT_DATASETS")
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


app_id = _text("FASTGPT_APP_ID")
provider = _text("MODEL_PROVIDER") or ("fastgpt" if app_id else "openai")

settings = Settings(
    fastgpt_url=_text("FASTGPT_URL"),
    fastgpt_key=_text("FASTGPT_KEY"),
    datasets=_datasets(),
    model_provider=provider,
    fastgpt_app_id=app_id,
    model_url=_text("MODEL_URL"),
    model_key=_text("MODEL_KEY"),
    model=_text("MODEL_NAME"),
    data_dir=Path(_text("DATA_DIR", str(ROOT / "data"))),
)

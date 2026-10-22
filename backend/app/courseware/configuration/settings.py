"""【配置适配·互动课件】从基础配置解析课件专用参数，保持 Agent 配置独立。"""

import copy
import importlib

FIELDS = {
    "fastgpt_url",
    "fastgpt_key",
    "fastgpt_app_id",
    "datasets",
    "model_provider",
    "model_url",
    "model_key",
    "model",
    "timeout",
    "model_read_timeout",
    "model_total_timeout",
    "search_mode",
    "similarity",
    "search_limit",
    "using_rerank",
}


def resolve_settings(base):
    result = copy.copy(base)
    try:
        overrides = importlib.import_module("backend.app.courseware_config").overrides
    except ModuleNotFoundError as exc:
        if exc.name != "backend.app.courseware_config":
            raise
        overrides = {}
    for name, value in overrides.items():
        if name not in FIELDS:
            raise ValueError("未知互动课件配置字段：" + name)
        setattr(result, name, value)
    return result

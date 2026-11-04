"""【配置适配·限时练习】解析练习专用模型与存储配置，不读取其他 Agent 的业务状态。"""

import copy


def practice_settings(base):
    config = copy.copy(base)
    for key, value in getattr(base, "timed_practice", {}).items():
        if key not in (
            "model_provider",
            "model_url",
            "model_key",
            "model",
            "fastgpt_url",
            "fastgpt_key",
            "fastgpt_app_id",
            "workflow_app_id",
            "repo_label_config",
            "datasets",
            "timeout",
            "model_read_timeout",
            "model_total_timeout",
        ):
            raise ValueError("未知限时练习配置字段：" + key)
        setattr(config, key, value)
    # 三个 Agent 共用知识库，忽略历史独立配置中的 datasets。
    config.datasets = copy.deepcopy(base.datasets)
    config.data_dir = base.data_dir / "timed-practice"
    return config

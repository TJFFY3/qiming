"""Connection overrides on settings.timed_practice; no business state is shared."""

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
            "datasets",
            "timeout",
            "model_read_timeout",
            "model_total_timeout",
        ):
            raise ValueError("未知限时练习配置字段：" + key)
        setattr(config, key, value)
    config.data_dir = base.data_dir / "timed-practice"
    return config

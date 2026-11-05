"""可选：复制为 courseware_config.py，为互动课件单独指定生成应用/模型。
不需要单独连接时无需复制，默认复用基础连接参数，各 Agent 的任务和提示词仍独立。
"""

overrides = {
    # 新生成链路使用统一工作流，可按需覆盖连接与标签条件：
    # 'workflow_app_id': '6ae34b10b1b18f9bb876d8ac',
    # 'repo_label_config': {},
    # 'model_provider': 'fastgpt',
    # 'fastgpt_app_id': '课件专用应用ID',
    # 'fastgpt_url': 'https://你的FastGPT域名/api',
    # 'fastgpt_key': '课件应用密钥',
    # 或独立 OpenAI 兼容连接：
    # 'model_provider': 'openai',
    # 'model_url': 'https://你的模型服务/v1',
    # 'model_key': '模型密钥',
    # 'model': '模型名称',
    # 'model_read_timeout': 300,  # 连续无数据的等待上限（秒）
    # 'model_total_timeout': 600,  # 单次模型调用的总预算（秒）
}

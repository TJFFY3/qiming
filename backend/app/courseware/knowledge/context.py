"""【上下文规则·互动课件】均衡节选已有来源；不发送知识库请求。"""

def source_context(sources):
    # 为每个当前或继承来源分配预算，避免新增资料挤占全部上下文。
    share = max(1, 48000 // max(1, len(sources)))
    return [
        {
            **{k: s.get(k) for k in ("id", "title", "category", "locator")},
            "evidence": s.get("evidence", "")[:share],
            "excerpted": len(s.get("evidence", "")) > share,
        }
        for s in sources
    ]

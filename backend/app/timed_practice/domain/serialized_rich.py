"""【规则处理·限时练习】将共享富文本解码工具适配为练习 Run 类型。"""

from backend.app.shared.chemistry.serialized_rich import decode_rich as _decode
from backend.app.timed_practice.domain.models import Run


def decode_rich(value):
    return _decode(value, Run)

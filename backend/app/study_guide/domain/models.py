"""【数据契约·导学案】定义接口输入、备课设置与修订请求的字段约束。"""

from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Options(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field("当前课时（默认）", max_length=500)
    duration: str = Field("按本课安排（默认）", max_length=200)
    tasks: str = Field("按本课安排（默认）", max_length=200)
    difficulty: str = Field("按本课安排（默认）", max_length=200)
    hints: str = Field("按本课安排（默认）", max_length=300)
    focus: list[str] = Field(
        default_factory=lambda: ["按本课安排（默认）"], max_length=10
    )
    extra: str = Field("", max_length=3000)


class SessionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chapter: str = Field("第三节 氧化还原反应", min_length=1, max_length=200)
    period: str = Field("第一课时", min_length=1, max_length=100)
    edition: str = Field("人教版 必修第一册", min_length=1, max_length=200)
    grade: str = Field("高一", min_length=1, max_length=50)
    options: Options = Field(default_factory=Options)


class GenerationInput(BaseModel):
    prompt: str = Field("请生成一份导学案。", min_length=1, max_length=8000)
    # Retained for compatibility with older clients; source verification no longer gates output.
    allow_draft: bool = True


class RevisionInput(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    base_version_id: str = Field(min_length=1, max_length=100)


class ReviewInput(BaseModel):
    verified: bool
    note: str = Field(min_length=1, max_length=1000)

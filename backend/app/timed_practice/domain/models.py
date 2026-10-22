"""【数据契约·限时练习】定义备课设置、题目、原图引用与整卷输出结构。"""

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT = "按本课安排（默认）"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class PracticeOptions(StrictModel):
    duration: str = Field(DEFAULT, min_length=1, max_length=200)
    score: str = Field(DEFAULT, min_length=1, max_length=200)
    questions: str = Field(DEFAULT, min_length=1, max_length=500)
    difficulty: str = Field(DEFAULT, min_length=1, max_length=200)
    origin: str = Field(DEFAULT, min_length=1, max_length=300)
    focus: list[str] = Field(default_factory=lambda: [DEFAULT], max_length=10)
    extra: str = Field("", max_length=3000)


class LessonSettings(StrictModel):
    chapter: str = Field("第三节 氧化还原反应", min_length=1, max_length=200)
    period: str = Field("第一课时", min_length=1, max_length=100)
    edition: str = Field("人教版 必修第一册", min_length=1, max_length=200)
    grade: str = Field("高一", min_length=1, max_length=50)
    options: PracticeOptions = Field(default_factory=PracticeOptions)


class GenerateInput(StrictModel):
    prompt: str = Field("请生成一份限时练习。", min_length=1, max_length=8000)
    allow_draft: bool = False


class ReviseInput(GenerateInput):
    base_version_id: str = Field(min_length=1, max_length=100)


class ReviewInput(StrictModel):
    verified: bool
    note: str = Field(min_length=1, max_length=1000)


class Isotope(StrictModel):
    mass: int = Field(ge=1, le=300)
    atomic: int = Field(ge=1, le=120)


class Run(StrictModel):
    text: str = Field(max_length=10000)
    sub: bool = False
    sup: bool = False
    charge: bool = False
    condition: bool = False
    bold: bool = False
    italic: bool = False
    underline: bool = False
    isotope: Isotope | None = None

    @model_validator(mode="after")
    def mutually_exclusive(self):
        if self.sub and (self.sup or self.charge):
            raise ValueError("上下标不能同时启用")
        return self


RichText = str | list[Run]


def text(value):
    return (
        value
        if isinstance(value, str)
        else "".join(r.text if isinstance(r, Run) else r["text"] for r in value)
    )


class QuestionImage(StrictModel):
    image_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    caption: str = Field(min_length=1, max_length=500)
    placement: Literal[
        "stem", "option_A", "option_B", "option_C", "option_D", "answer", "explanation"
    ] = "stem"


class Question(StrictModel):
    stem: RichText
    options: list[RichText] | None = Field(None, min_length=4, max_length=4)
    answer: RichText
    explanation: RichText
    score: float = Field(ge=0, le=1000, strict=True)
    minutes: float = Field(gt=0, le=180, strict=True)
    difficulty: Literal["基础", "中档", "较难"]
    source_ids: list[str] = Field(default_factory=list, max_length=20)
    origin: Literal["original", "adapted", "new"]
    work_lines: int = Field(2, ge=1, le=20, strict=True)
    images: list[QuestionImage] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def nonempty(self):
        for key in ("stem", "answer", "explanation"):
            v = text(getattr(self, key))
            if not v.strip() or len(v) > 10000:
                raise ValueError(key + " 不能为空或超过10000字符")
        if self.options and any(
            not text(v).strip() or len(text(v)) > 3000 for v in self.options
        ):
            raise ValueError("选项不能为空或超过3000字符")
        return self


class PracticeContent(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    duration: float = Field(gt=0, le=180, strict=True)
    total_score: float = Field(gt=0, le=1000, strict=True)
    choice: list[Question] = Field(default_factory=list, max_length=60)
    written: list[Question] = Field(default_factory=list, max_length=40)
    optional: list[Question] = Field(default_factory=list, max_length=10)
    source_gaps: list[str] = Field(default_factory=list, max_length=300)
    conflicts: list[str] = Field(default_factory=list, max_length=30)

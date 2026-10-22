"""【数据契约·互动课件】定义备课设置、逐页内容与局部修订结果的结构约束。"""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT = "按本课安排（默认）"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CoursewareOptions(StrictModel):
    scope: str = Field("当前课时（默认）", min_length=1, max_length=500)
    duration: str = Field(DEFAULT, min_length=1, max_length=200)
    pages: str = Field(DEFAULT, min_length=1, max_length=200)
    exercises: str = Field(DEFAULT, min_length=1, max_length=500)
    teaching: str = Field(DEFAULT, min_length=1, max_length=200)
    focus: list[str] = Field(default_factory=lambda: [DEFAULT], max_length=10)
    extra: str = Field("", max_length=3000)


class CoursewareSettings(StrictModel):
    chapter: str = Field("第三节 氧化还原反应", min_length=1, max_length=200)
    period: Literal["第一课时", "第二课时"] = "第一课时"
    edition: str = Field("人教版 必修第一册", min_length=1, max_length=200)
    grade: Literal["高一", "高二", "高三"] = "高一"
    format: Literal["传统 PPT"] = "传统 PPT"
    options: CoursewareOptions = Field(default_factory=CoursewareOptions)


class Generation(StrictModel):
    prompt: str = Field("请生成互动课件。", min_length=1, max_length=8000)
    allow_draft: bool = True


class Revision(Generation):
    base_version_id: str = Field(min_length=1, max_length=100)
    allow_full_revision: bool = False


class Run(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    text: str = Field(max_length=1000)
    sub: bool = False
    sup: bool = False
    bold: bool = False
    italic: bool = False
    underline: bool = False
    charge: bool = False
    condition: bool = False
    isotope: dict[str, int] | None = None

    @field_validator("isotope")
    @classmethod
    def isotope_numbers(cls, value):
        if value is not None and (
            set(value) != {"mass", "atomic"} or any(v <= 0 for v in value.values())
        ):
            raise ValueError("同位素需要正整数 mass 和 atomic")
        return value


class Slide(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    stage: Literal[
        "启",
        "探",
        "析",
        "辩",
        "辩—自由讨论",
        "辩—预设讨论",
        "辩—自由展示",
        "辩—预设展示",
        "辩—梳理内化",
    ]
    paragraphs: list[str | list[Run]] = Field(min_length=1, max_length=6)
    notes: str = Field("", max_length=5000)
    # Images cannot be selected by arbitrary model-provided file paths.
    image: None = None
    image_id: str | None = Field(None, pattern=r"^[0-9a-f]{24}$")
    image_caption: str = Field("", max_length=18)

    @field_validator("paragraphs")
    @classmethod
    def complete_content(cls, value):
        texts = [p if isinstance(p, str) else "".join(r.text for r in p) for p in value]
        if any(not text.strip() for text in texts):
            raise ValueError("课件段落不能为空，请提供完整教学内容")
        if any(re.search(r"X{3,}|TODO|待填写", text, re.IGNORECASE) for text in texts):
            raise ValueError(
                "课件包含未填写的占位内容；未提供的姓名、日期请删除，不要编造"
            )
        return value


class Deck(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    slides: list[Slide] = Field(min_length=1, max_length=60)
    # Stored decks accumulate provenance issues across revisions. The per-patch
    # limit belongs to RevisionResult, not to this historical merged record.
    source_gaps: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class PageChange(StrictModel):
    page: int = Field(ge=1, le=60)
    slide: Slide


class RevisionResult(StrictModel):
    mode: Literal["patch", "full"]
    title: str | None = Field(None, min_length=1, max_length=200)
    changes: list[PageChange] = Field(default_factory=list, max_length=60)
    deck: Deck | None = None
    source_gaps: list[str] = Field(default_factory=list, max_length=30)
    conflicts: list[str] = Field(default_factory=list, max_length=30)

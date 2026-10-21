"""Variable-size practice contracts and two independent template-based Word artifacts."""

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from pydantic import ValidationError

VENDOR = Path(__file__).resolve().parents[3] / "vendor" / "chemistry"
if str(VENDOR / "scripts") not in sys.path:
    sys.path.insert(0, str(VENDOR / "scripts"))
from docx_tools import _template, _p, _title, _heading, _save  # noqa: E402
from chemistry_runs import add_docx_runs, normalize_runs  # noqa: E402
from validate_outputs import validate_paths  # noqa: E402
from .models import PracticeContent, text  # noqa: E402
from ..publication import clean_public, clean_office_in_place  # noqa: E402
from .equations import format_runs, format_content  # noqa: E402
from .word_equations import format_word_conditions  # noqa: E402
from .serialized_rich import decode_rich  # noqa: E402
from ..content_quality import LEAK  # noqa: E402
from ..chemistry_format import _rich as normalize_equations  # noqa: E402


def normalized(value):
    return re.sub(r"[\s\[\]。；，、:：;,.＿_]+", "", text(normalize_runs(value)))


def canonical_rich(value):
    value = decode_rich(value)
    if isinstance(value, list):
        value = [
            {
                k: v
                for k, v in run.items()
                if k == "text" or (v is not False and v is not None)
            }
            for run in value
        ]
    return format_runs(normalize_runs(normalize_equations(value)))


EDITORIAL = re.compile(
    r"(?:本题|该题|此题).{0,24}已(?:修改|改写|改为)|"
    r"(?:请|需要)(?:删除|移除).{0,16}(?:编辑说明|本段说明)|"
    r"(?:以下|本段)(?:为|是)(?:内部)?编辑说明"
)


def check_teaching_text(content):
    for group in ("choice", "written", "optional"):
        for index, question in enumerate(content.get(group, []), 1):
            values = [question[field] for field in ("stem", "answer", "explanation")]
            values += question.get("options") or []
            for value in values:
                prose = text(value)
                if LEAK.search(prose) or EDITORIAL.search(prose):
                    raise ValueError(
                        f"{group}第{index}题混入内部编辑说明，请移除生成或修改说明，保留教学内容"
                    )


def validate_practice_word(paths):
    validation = validate_paths(paths)
    retained = []
    for issue in validation["issues"]:
        if (
            issue.get("code") == "DOCX_EDIT_RESIDUE"
            and issue.get("message") == "Possible editing residue: 注："
        ):
            # A note marker (also inside 标注：) says nothing about its meaning.
            # Teaching text is checked before export; keep all OOXML checks.
            validation["warnings"].append(
                {
                    **issue,
                    "code": "DOCX_TEACHING_NOTE",
                    "message": "包含补充说明，已保留原文。",
                }
            )
        else:
            retained.append(issue)
    validation["issues"] = retained
    validation["passed"] = not retained
    return validation


def validate_content(raw, requirements, sources):
    try:
        content = PracticeContent.model_validate(raw).model_dump(exclude_none=True)
    except ValidationError as exc:
        raise ValueError(str(exc)) from None
    check_teaching_text(content)
    questions = content["choice"] + content["written"] + content["optional"]
    if not content["choice"] and not content["written"]:
        raise ValueError("至少需要一道必做题")
    if len(json.dumps(content, ensure_ascii=False)) > 180000:
        raise ValueError("试卷内容过长")
    if not math.isclose(content["total_score"], requirements["total_score"]):
        raise ValueError("满分与教师要求不一致")
    if not math.isclose(content["duration"], requirements["duration"]):
        raise ValueError("用时与教师要求不一致")
    if not math.isclose(
        sum(q["score"] for q in content["choice"] + content["written"]),
        content["total_score"],
    ):
        raise ValueError("必做题分值合计必须等于满分")
    estimate = sum(q["minutes"] for q in content["choice"] + content["written"])
    if estimate > content["duration"]:
        raise ValueError("必做题预估用时超过指定用时，请调整题量或难度，不得虚填估时")
    if "choice_score" in requirements and estimate < 30:
        raise ValueError("默认试卷必做预估用时应为30至35分钟")
    for group in ("choice", "written", "optional"):
        if (
            group + "_count" in requirements
            and len(content[group]) != requirements[group + "_count"]
        ):
            raise ValueError(group + "题量与教师要求不一致")
    if (
        "written_score" in requirements
        and sum(q["score"] for q in content["written"]) != requirements["written_score"]
    ):
        raise ValueError("默认II卷须合计44分")
    if "choice_score" in requirements and any(
        q["score"] != requirements["choice_score"] for q in content["choice"]
    ):
        raise ValueError("默认单选每题4分")
    ids = {s["id"]: s for s in sources}
    seen = set()
    for index, q in enumerate(questions, 1):
        key = normalized(q["stem"])
        if key in seen:
            raise ValueError("题干重复，请去重")
        seen.add(key)
        if any(ref not in ids for ref in q["source_ids"]):
            raise ValueError("题目引用不存在的来源ID")
        format_ids = [
            ref
            for ref in q["source_ids"]
            if re.search(r"模板|格式样例|测试样例|示例|样例", ids[ref]["title"])
        ]
        if format_ids:
            remaining = [ref for ref in q["source_ids"] if ref not in format_ids]
            if (
                not remaining
                and q["origin"] != "new"
                and requirements["origin"] != "any"
            ):
                raise ValueError(
                    "模板和格式样例不能作为原题或改编题题源，请补充实际题源"
                )
            q["source_ids"] = remaining
            content["source_gaps"].append(
                f"第{index}题的模板/样例引用仅作格式参考，已从题源中移除，需教师核对实际出处。"
            )
            if not remaining:
                q["origin"] = "new"
        if not q["source_ids"] and q["origin"] != "new":
            raise ValueError("原题和改编题必须关联实际来源")
        if requirements["origin"] == "original" and q["origin"] != "original":
            raise ValueError("只用原题时不能使用改编或自编题")
        if requirements["origin"] == "adapted" and q["origin"] == "new":
            raise ValueError("当前出题方式不允许自编题")
        if q["origin"] == "original":
            evidence = "".join(
                normalized(ids[ref]["evidence"]) for ref in q["source_ids"]
            )
            if key not in evidence or any(
                normalized(option) not in evidence for option in q.get("options", [])
            ):
                if requirements["origin"] == "any":
                    q["origin"] = "new"
                    content["source_gaps"].append(
                        f"第{index}题未能定位完整原题，按自编题处理；引用仅作知识点参考。"
                    )
                else:
                    raise ValueError(
                        "原题题干或选项无法在关联来源摘录中定位，请补充完整原题"
                    )
    for q in content["choice"]:
        if not q.get("options") or text(q["answer"]) not in ("A", "B", "C", "D"):
            raise ValueError("单选题必须有4个选项及A/B/C/D答案")
        if q["score"] <= 0:
            raise ValueError("必做题分值必须为正")
    if any(q.get("options") for q in content["written"]):
        raise ValueError("解答题不能带选择项")
    if any(q["score"] <= 0 for q in content["written"]):
        raise ValueError("必做题分值必须为正")
    if any(q["score"] != 0 for q in content["optional"]):
        raise ValueError("选做题不计分")
    for q in questions:
        for field in ("stem", "answer", "explanation"):
            q[field] = canonical_rich(q[field])
        if q.get("options"):
            options = []
            for i, option in enumerate(q["options"]):
                pattern = r"^\s*" + "ABCD"[i] + r"[.．、:：]\s*"
                if isinstance(option, str):
                    option = re.sub(pattern, "", option)
                elif option:
                    option = [dict(r) for r in option]
                    option[0]["text"] = re.sub(pattern, "", option[0]["text"])
                if not text(option).strip():
                    raise ValueError("去除选项标号后内容不能为空")
                options.append(canonical_rich(option))
            q["options"] = options
    if len(json.dumps(content, ensure_ascii=False)) > 180000:
        raise ValueError("规范化后的试卷内容过长，请减少题量或解析长度")
    return content


def source_issues(content, sources):
    issues = []
    for index, q in enumerate(
        content["choice"] + content["written"] + content["optional"], 1
    ):
        if q["origin"] == "new":
            issues.append(f"第{index}题为自编题，需教师审核")
    return list(dict.fromkeys(issues + content["source_gaps"] + content["conflicts"]))


def render(content, sources, directory, draft):
    check_teaching_text(content)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    paper = _template("限时练模板.docx")
    answers = _template("限时练模板.docx")
    content = format_content(clean_public(content))
    title = content["title"]
    _title(paper, title, 14)
    _title(answers, title + " 答案与解析", 14)
    _p(paper, "姓名________　班级________　组号________")
    _p(
        answers,
        f"满分：{content['total_score']:g}分；建议用时：{content['duration']:g}分钟；必做预估：{sum(q['minutes'] for q in content['choice'] + content['written']):g}分钟。",
    )
    ids = {s["id"]: s for s in sources}
    number = 1
    for key, label in [
        ("choice", "一、单项选择题"),
        ("written", "二、填空及简答题"),
        ("optional", "【选做题，不计入必做分数与用时】"),
    ]:
        qs = content[key]
        if not qs:
            continue
        _heading(paper, label)
        _heading(answers, label)
        for q in qs:
            p = _p(
                paper, f"{number}. " + (f"（{q['score']:g}分）" if q["score"] else "")
            )
            add_docx_runs(p, q["stem"])
            if q.get("options"):
                for letter, option in zip("ABCD", q["options"]):
                    p = _p(paper, letter + ". ")
                    add_docx_runs(p, option)
            else:
                for _ in range(q["work_lines"]):
                    _p(paper, [{"text": "　" * 30, "underline": True}])
            _heading(
                answers,
                f"{number}. 难度：{q['difficulty']}　分值：{q['score']:g}　预估用时：{q['minutes']:g}分钟",
            )
            for field, label2 in [("answer", "答案："), ("explanation", "解析：")]:
                p = _p(answers, label2)
                add_docx_runs(p, q[field])
            origin = {
                "original": "原题",
                "adapted": "改编题",
                "new": "自编题，需教师审核",
            }[q["origin"]]
            _p(
                answers,
                "题源："
                + origin
                + "；"
                + "；".join(
                    ids[r]["title"] + " " + ids[r]["locator"] for r in q["source_ids"]
                ),
            )
            number += 1
        if key == "choice":
            _heading(paper, "选择题答题表")
            # Split large cards to preserve the template printable width.
            for start in range(0, len(qs), 14):
                size = min(14, len(qs) - start)
                table = paper.add_table(rows=2, cols=size + 1)
                table.style = "Table Grid"
                table.cell(0, 0).text = "题号"
                table.cell(1, 0).text = "答案"
                for i in range(size):
                    table.cell(0, i + 1).text = str(start + i + 1)
    format_word_conditions(paper)
    format_word_conditions(answers)
    _save(paper, directory / "paper.docx")
    _save(answers, directory / "answers.docx")
    for name in ("paper.docx", "answers.docx"):
        clean_office_in_place(directory / name)
    validation = validate_practice_word(
        [directory / "paper.docx", directory / "answers.docx"]
    )
    for kind in ("issues", "warnings"):
        for item in validation.get(kind, []):
            item["file"] = Path(item["file"]).name
    if not validation["passed"]:
        raise ValueError(
            "Word结构校验失败：" + json.dumps(validation["issues"], ensure_ascii=False)
        )
    digest = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()
    report = dict(
        draft=False,
        source_issues=source_issues(content, sources),
        content_sha256=digest,
        validation=validation,
        review_required=[
            "教师核对题干、答案、难度及来源",
            "Word/WPS分页、化学EQ域与答题空间视觉效果",
        ],
    )
    for name, value in [
        ("content.json", content),
        ("generation_report.json", report),
        ("sources.json", sources),
    ]:
        (directory / name).write_text(
            json.dumps(
                clean_public(value), ensure_ascii=False, indent=2, allow_nan=False
            ),
            encoding="utf-8",
        )
    return report

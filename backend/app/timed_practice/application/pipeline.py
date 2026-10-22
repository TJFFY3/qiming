"""【流程编排·限时练习】串联需求解析、题源整理、模型、内容规则与双 Word 生成。"""

import copy
import json
import shutil
import uuid
import tempfile
from pathlib import Path
from backend.app.timed_practice.domain.models import PracticeContent
from backend.app.timed_practice.llm.client import ModelOutputError
from backend.app.timed_practice.llm.prompts import SYSTEM
from backend.app.timed_practice.domain.requirements import resolve_requirements
from backend.app.timed_practice.domain.revision import validate_revision_scope
from backend.app.timed_practice.knowledge.context import prepare_source_context
from backend.app.timed_practice.tools.documents import validate_content, render
from backend.app.shared.chemistry.validation import validate_practice
from backend.app.timed_practice.storage.store import now, PracticeConflict
from backend.app.timed_practice.tools.images import prepare_images, question_image_catalog


class PracticePipeline:
    """限时练习用例编排；题量等确定性规则与模型生成分别执行。"""

    def __init__(self, settings, store, retriever, model, image_transport=None):
        self.settings = settings
        self.store = store
        self.retriever = retriever
        self.model = model
        self.image_transport = image_transport

    def stage(self, jid, label):
        job = self.store.get_job(jid)
        if job["status"] not in ("queued", "running"):
            raise PracticeConflict("任务已终止，请重新提交")
        stages = job["stages"]
        for s in stages:
            if s["status"] == "running":
                s["status"] = "completed"
        stages.append(dict(label=label, status="running", started_at=now()))
        self.store.update_job(jid, status="running", stages=stages)

    def model_call(self, jid, messages, attempt):
        streaming = getattr(self.model, "generate_json_with_progress", None)
        if not streaming:
            return self.model.generate_json(messages)
        initial = self.store.get_job(jid)["stages"][-1]["label"].split("（已接收")[0]

        def update(value):
            job = self.store.get_job(jid)
            if job["status"] not in ("queued", "running"):
                raise PracticeConflict("任务已终止，请重新提交")
            stages = job["stages"]
            count = value["received_chars"]
            stages[-1]["label"] = initial + (f"（已接收 {count} 字）" if count else "")
            self.store.update_job(
                jid, model_progress={**value, "attempt": attempt + 1}, stages=stages
            )

        return streaming(messages, update)

    def run(self, jid):
        destination = None
        try:
            job = self.store.get_job(jid)
            request = job["request"]
            sid = job["session_id"]
            session = self.store.get_session(sid)
            revision = request["kind"] == "revision"
            base = session["versions"][-1] if session["versions"] else None
            self.stage(jid, "保存限时练习要求")
            prior_requirements = copy.deepcopy(base.get("requirements", {})) if base else {}
            if base and "question_setting" not in prior_requirements:
                # 【兼容规则】从原任务恢复旧设置，识别教师的新设置，不重写历史版本。
                prior_job = next((
                    item for item in self.store.jobs_for(sid)
                    if item.get("version_id") == base["id"]
                ), None)
                if prior_job:
                    old_options = prior_job["request"].get("teacher_settings", {}).get("options", {})
                    if "questions" in old_options:
                        prior_requirements["question_setting"] = old_options["questions"]
            # 【规则处理】合并正文与设置；相对题量修改基于当前版本计算。
            requirements = resolve_requirements(
                request["teacher_settings"],
                request["prompt"],
                base["content"] if base else None,
                prior_requirements,
            )
            self.store.update_job(jid, effective_requirements=requirements)
            self.stage(jid, "整理题源与本课资料")
            # 【资料准备】修订复用原始证据；新增资料只合并进本次来源快照。
            if revision:
                sources = copy.deepcopy(base["sources"])
                current = {s["id"]: s for s in session["sources"]}
                for source in sources:
                    reviewed = current.get(source["id"])
                    if reviewed and reviewed.get("evidence") == source.get("evidence"):
                        source["verified"] = bool(reviewed.get("verified"))
                        source["review_note"] = reviewed.get("review_note", "")
                merged = {s["id"]: s for s in sources}
                for source in session["sources"] + request["resources"]:
                    merged[source["id"]] = {
                        k: v
                        for k, v in source.items()
                        if k not in ("file_path", "text", "pages")
                    }
                sources = list(merged.values())
            else:
                query = (
                    " ".join(
                        str(request["teacher_settings"][key])
                        for key in ("edition", "grade", "chapter", "period")
                    )
                    + " "
                    + request["prompt"]
                )
                # 【知识库调用】首次生成按本课信息检索，上传资料稍后合并。
                hits = (
                    self.retriever.search(query)
                    if self.settings.fastgpt_url or not request["resources"]
                    else []
                )
                old = {s["id"]: s for s in session["sources"]}
                sources = []
                for s in hits:
                    s = copy.deepcopy(s)
                    prior = old.get(s["id"], {})
                    if prior.get("evidence") == s.get("evidence"):
                        s["verified"] = prior.get("verified", s.get("verified", False))
                    sources.append(s)
                sources += [
                    {
                        k: v
                        for k, v in r.items()
                        if k not in ("file_path", "text", "pages")
                    }
                    for r in request["resources"]
                ]
                sources = list({s["id"]: s for s in sources}.values())
                self.store.update_session(sid, lambda s: s.update(sources=sources))
            if sum(len(s.get("evidence", "")) for s in sources) > 120000:
                raise ValueError("参考资料超过120000字符，请减少本课资料")
            self.stage(
                jid, "生成试题与独立答案解析" if not revision else "按要求修订当前练习"
            )
            # 【上下文规则】本地选择相关片段；保存的完整来源证据不被截断。
            model_sources, context_stats = prepare_source_context(
                sources, request["teacher_settings"], requirements["origin"]
            )
            self.store.update_job(jid, model_context=context_stats)
            context = dict(
                teacher_settings=request["teacher_settings"],
                request=request["prompt"],
                effective_requirements=requirements,
                sources=model_sources,
                image_catalog=[
                    {k: v for k, v in image.items() if k != "url"}
                    for image in question_image_catalog(sources)
                ],
                source_context_notes="来源为本课优先的预算内片段；excerpt_truncated表示仅节选，不得据此补造原题缺失内容。原始来源快照保留完整资料。",
            )
            if revision:
                context["current_practice"] = base["content"]
            # 【提示词组装】命题协议、输出 Schema 与教师需求共同构成模型输入。
            messages = [
                dict(
                    role="system",
                    content=SYSTEM
                    + "\nSchema:\n"
                    + json.dumps(
                        PracticeContent.model_json_schema(),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                ),
                dict(
                    role="user",
                    content=json.dumps(
                        context, ensure_ascii=False, separators=(",", ":")
                    ),
                ),
            ]
            content = None
            # 【模型调用与修复】首次生成 + 最多两轮 JSON 或内容修复。
            for attempt in range(3):
                try:
                    raw = self.model_call(jid, messages, attempt)
                except ModelOutputError as exc:
                    diagnostics = self.settings.data_dir / sid / "diagnostics" / jid
                    diagnostics.mkdir(parents=True, exist_ok=True)
                    (diagnostics / f"attempt-{attempt + 1}.json").write_text(
                        json.dumps(
                            {
                                "attempt": attempt + 1,
                                "error": self.settings.redact(str(exc)),
                                "response_text": self.settings.redact(
                                    exc.response_text
                                ),
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    if attempt == 2:
                        raise ValueError(
                            "限时练习模型输出处理失败，已修复两轮：" + str(exc)
                        ) from None
                    if exc.response_text:
                        messages.append(
                            dict(role="assistant", content=exc.response_text[:80000])
                        )
                    messages.append(
                        dict(
                            role="user",
                            content="上次响应无法解析为JSON。请修正下面的具体错误，直接返回符合Schema的完整JSON对象，不要附加说明或省略内容；正确转义字符串内的引号、换行和反斜杠，化学富文本必须使用真正的扁平run数组，不得嵌入未转义的JSON。保留原题量、用时和分值要求。错误："
                            + str(exc),
                        )
                    )
                    continue
                try:
                    # 【规则处理】校验题量、总分、估时、题源、方程式与修订范围。
                    content = validate_content(raw, requirements, sources)
                    validate_practice(content)
                    if revision:
                        validate_revision_scope(content, base["content"], request["prompt"])
                    if revision and content == base["content"]:
                        raise ValueError(
                            "修改没有实际内容变化，请按教师要求修改目标题目"
                        )
                    break
                except ValueError as exc:
                    if attempt == 2:
                        raise ValueError(
                            "限时练习内容校验失败，已修复两轮：" + str(exc)
                        ) from None
                    messages += [
                        dict(
                            role="assistant",
                            content=json.dumps(raw, ensure_ascii=False),
                        ),
                        dict(
                            role="user",
                            content="仅修复以下错误，保留其他内容：" + str(exc),
                        ),
                    ]
            self.stage(jid, "最终方程式校验、题量分值估时与两份Word装配")
            vid = uuid.uuid4().hex
            destination = self.settings.data_dir / sid / "versions" / vid
            with tempfile.TemporaryDirectory(prefix="practice-images-") as temporary:
                cached = Path(temporary) / "images"
                if revision and (Path(base["directory"]) / "images").is_dir():
                    shutil.copytree(Path(base["directory"]) / "images", cached)
                assets = prepare_images(
                    content,
                    sources,
                    cached,
                    transport=self.image_transport,
                    allowed_origin=self.settings.fastgpt_url
                    or "https://cloud.fastgpt.cn",
                )
                # 【文档工具】用已校验内容生成学生卷与独立答案解析卷。
                report = render(
                    content, sources, destination, False, image_assets=assets
                )
            number = f"v{len(session['versions']) + 1:03d}"
            version = dict(
                id=vid,
                number=number,
                parent_id=base["id"] if revision else None,
                created_at=now(),
                content=content,
                sources=sources,
                report=report,
                directory=str(destination),
                requirements=requirements,
            )
            self.stage(jid, "保存限时练习不可变版本")
            # 【状态存储】同时保存需求、来源和两份产物对应的不可变版本。
            self.store.publish(jid, version)
        except Exception as exc:
            if destination and destination.exists():
                shutil.rmtree(destination)
            message = (
                self.settings.redact(str(exc))
                if isinstance(exc, (ValueError, KeyError, OSError))
                else "限时练习任务执行失败，请检查服务端后重试"
            )
            failed = self.store.get_job(jid)
            for stage in failed["stages"]:
                if stage["status"] == "running":
                    stage.update(status="failed", ended_at=now())
            self.store.update_job(
                jid, status="failed", error=message[:2500], stages=failed["stages"]
            )

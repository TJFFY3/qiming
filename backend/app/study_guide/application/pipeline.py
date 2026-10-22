"""【流程编排·导学案】串联资料、提示词、模型、规则和 Word 工具；校验通过后发布版本。"""

import copy
import json
import shutil
import uuid
from pathlib import Path
from backend.app.study_guide.storage.store import now
from backend.app.study_guide.llm.client import ModelOutputError, ModelServiceError
from backend.app.study_guide.tools.images import image_catalog, ImageAssetError
from backend.app.study_guide.llm.prompts import SYSTEM, instruction_text
from backend.app.shared.chemistry.formatting import normalize_chemistry
from backend.app.shared.chemistry.validation import validate_study_guide_result
from backend.app.shared.chemistry.repair import EquationBalanceError, equation_repair_messages, apply_equation_repairs
from backend.app.shared.rules.content_quality import check_student_content
from backend.app.study_guide.knowledge.context import revision_source_context
from backend.app.study_guide.domain.table_repair import (
    repair_empty_headers,
    header_target,
    apply_header_repair,
    header_repair_messages,
    is_header_error,
    ContentRepairFailure,
)


class Pipeline:
    """导学案用例编排；模型、检索器和文档引擎由外部注入，便于独立测试。"""

    def __init__(self, settings, store, retriever, model, documents):
        self.settings, self.store, self.retriever, self.model, self.documents = (
            settings,
            store,
            retriever,
            model,
            documents,
        )

    def start_generation(self, session_id, request):
        return self.store.create_job(session_id, {**request, "kind": "generation"})

    def start_revision(self, session_id, request):
        return self.store.create_job(session_id, {**request, "kind": "revision"})

    def stage(self, job_id, index, label):
        job = self.store.get_job(job_id)
        stages = job["stages"]
        for item in stages:
            if item["status"] == "running":
                item.update(status="completed", ended_at=now())
        stages.append(
            {"index": index, "label": label, "status": "running", "started_at": now()}
        )
        self.store.update_job(job_id, status="running", stages=stages)

    @staticmethod
    def controlled_payload(raw, sources):
        # 【来源规则】只采用服务器保存的证据，不能相信模型返回的来源或核验标记。
        gaps = raw.get("source_gaps", [])
        conflicts = raw.get("source_conflicts", [])
        if not isinstance(gaps, list) or not all(isinstance(x, str) for x in gaps):
            raise ValueError("source_gaps 必须为字符串数组")
        if not isinstance(conflicts, list) or not all(
            isinstance(x, str) for x in conflicts
        ):
            raise ValueError("source_conflicts 必须为字符串数组")
        return {
            "outline": raw.get("outline", raw),
            "sources": copy.deepcopy(sources),
            "source_gaps": gaps,
            "source_conflicts": conflicts,
        }

    @staticmethod
    def reject_noop(report, base, destination):
        if report["content_sha256"] == base["content_sha256"]:
            shutil.rmtree(destination)
            raise ValueError(
                "本次修改没有实际内容变化。必须按教师要求修改对应任务，不能只原样复制或替换无关留白块。"
            )

    def run(self, job_id):
        destination = None
        published = False
        try:
            job = self.store.get_job(job_id)
            request = job["request"]
            sid = job["session_id"]
            session = self.store.get_session(sid)
            teacher_settings = request.get("teacher_settings", session["settings"])
            revision = request["kind"] == "revision"
            self.stage(job_id, 0, "教师要求与课时已保存")
            self.stage(
                job_id,
                1,
                "检索教材与整理参考资料" if not revision else "读取当前版本与资料快照",
            )
            # 【资料准备】修订复用版本证据；首次生成才检索知识库。
            if revision:
                base = next(
                    v
                    for v in session["versions"]
                    if v["id"] == request["base_version_id"]
                )
                # 【来源规则】保留检索证据，上传资料使用当前集合；历史版本快照保持不变。
                sources = [
                    copy.deepcopy(source)
                    for source in base["sources"]
                    if source.get("source_type") != "upload"
                    and source.get("locator") != "上传原文件（页码见摘录，非印刷页码）"
                ]
            else:
                query = (
                    " ".join(
                        str(teacher_settings.get(k, ""))
                        for k in ("edition", "grade", "chapter", "period")
                    )
                    + " "
                    + instruction_text(request.get("prompt", ""))
                )
                # 【知识库规则】显式配置 FastGPT 后必须检索成功，不能用上传资料掩盖连接失败。
                if session["resources"] and not self.settings.fastgpt_url:
                    sources = []
                else:
                    # 【知识库调用】返回来源证据，不是教学内容生成。
                    sources = self.retriever.search(query)
            previous = {x["id"]: x for x in session["sources"]}
            for source in sources:
                old = previous.get(source["id"])
                if old and old.get("evidence") == source["evidence"]:
                    source["verified"] = bool(old.get("verified"))
                    source["review_note"] = old.get("review_note", "")
            sources += [
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("file_path", "text", "pages")
                }
                | {"evidence": r["text"], "source_type": "upload"}
                for r in session["resources"]
            ]
            sources = list({s["id"]: s for s in sources}.values())
            if sum(len(s["evidence"]) for s in sources) > 120000:
                raise ValueError(
                    "资料总量超过120000字符，请减少上传资料或缩小检索范围"
                )
            self.store.update_session(sid, lambda s: s.update(sources=sources))
            if not sources and not revision:
                raise ValueError(
                    "未检索到本课资料，请调整章节、上传资料或检查知识库"
                )
            self.stage(
                job_id, 2, "生成教学内容" if not revision else "按要求修改教学内容"
            )
            # 【提示词组装】将可信来源与图片目录交给模型，隐藏图片原始地址。
            context = {
                "image_catalog": [
                    {key: value for key, value in image.items() if key != "url"}
                    for image in image_catalog(sources)
                ],
                "teacher_settings": teacher_settings,
                "request": request["prompt"],
                "sources": sources,
            }
            system = (
                SYSTEM
                + "\noutline JSON Schema:\n"
                + json.dumps(self.documents.schema, ensure_ascii=False)
            )
            if revision:
                context["current_outline"] = base["content"]
                context["sources"] = revision_source_context(sources, request["prompt"])
                context["source_context_notes"] = (
                    "资料在总量预算内优先节选与修改要求相关的原文，[…]表示省略。"
                    "excerpt_truncated=true不代表已读完整资料；若节选不能支持修改，"
                    "请记录source_gaps，不得补造缺失的实验条件或证据。"
                )
                system += '\n修改时返回 {"mode":"patch","changes":[{"block_id":"现有ID","replacement":[标准块]}]}。仅替换现有块，保留未涉及内容。若明确要求改目标、标题或新增章节，返回 {"mode":"full","outline":完整对象,"source_gaps":[],"source_conflicts":[]}。'
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ]
            if revision:
                messages.append(
                    {
                        "role": "user",
                        "content": "当前唯一修改任务："
                        + request["prompt"]
                        + "。请根据 current_outline 定位实际任务块，返回有内容变化的补丁。除非教师要求，不要修改留白说明块；必须保留未涉及内容。",
                    }
                )
            number = len(session["versions"]) + 1
            version_id = uuid.uuid4().hex
            destination = self.settings.data_dir / sid / "versions" / version_id
            version_name = f"v{number:03d}"
            result = None
            last_error = None
            raw, target, repairs = None, None, []
            header_feedback = []
            equation_targets, equation_feedback = None, []
            # 【模型调用与修复】首次生成 + 最多两轮内容修复；服务故障直接失败。
            for attempt in range(3):
                equation_response = None
                try:
                    if equation_targets is not None:
                        equation_response = self.model.generate_json(
                            equation_repair_messages(equation_targets, context={
                                "teacher_request": request["prompt"], "teacher_settings": teacher_settings,
                                "sources": revision_source_context(sources, "\n".join(str(t["value"]) for t in equation_targets)),
                            }) + equation_feedback
                        )
                        raw, notes = apply_equation_repairs(raw, equation_targets, equation_response)
                        repairs.extend(notes)
                        equation_targets, equation_feedback = None, []
                    elif target is not None:
                        response = self.model.generate_json(
                            header_repair_messages(target) + header_feedback
                        )
                        raw, note = apply_header_repair(raw, target, response)
                        repairs.append(note)
                        target = None
                        header_feedback = []
                    else:
                        raw = self.model.generate_json(messages)
                        repairs = []
                    # 【规则处理】先做确定性格式修复，再验证方程式和学生正文。
                    raw, chemistry_repairs = normalize_chemistry(raw)
                    repairs.extend(chemistry_repairs)
                    raw, automatic = repair_empty_headers(raw)
                    repairs.extend(automatic)
                    validate_study_guide_result(raw)
                    if attempt == 0:
                        self.stage(job_id, 3, "校验内容结构与来源")
                    check_student_content(raw)
                    if revision and raw.get("mode") == "patch":
                        source_payload = self.controlled_payload(raw, sources)
                        patch = {
                            "base_sha256": base["content_sha256"],
                            "changes": raw.get("changes"),
                        }
                        # 【修订规则】底层工具先校验块 ID、基线哈希和所有修改，再写入新目录。
                        # 【文档工具】校验块 ID、基线哈希与补丁，再写入新版本目录。
                        result = self.documents.revise(
                            Path(base["directory"]), patch, destination, version_name,
                            sources=sources,
                            source_gaps=source_payload["source_gaps"],
                            source_conflicts=source_payload["source_conflicts"],
                        )
                        self.reject_noop(result, base, destination)
                        change_kind = "局部修改"
                        break
                    if revision and raw.get("mode") != "full":
                        raise ValueError("修改必须返回 mode=patch 或 mode=full")
                    payload = self.controlled_payload(raw, sources)
                    if revision:
                        old_input = json.loads(
                            (Path(base["directory"]) / "source_input.json").read_text()
                        )
                        payload["source_gaps"] = list(
                            dict.fromkeys(
                                old_input.get("source_gaps", [])
                                + payload["source_gaps"]
                            )
                        )
                        payload["source_conflicts"] = list(
                            dict.fromkeys(
                                old_input.get("source_conflicts", [])
                                + payload["source_conflicts"]
                            )
                        )
                    validated = self.documents.validate(payload)
                    check_student_content(validated["outline"])
                    # 【来源规则】核验状态用于提示教师，不阻止生成与导出。
                    allow = True
                    previous = (
                        {
                            "version": base["number"],
                            "content_sha256": base["content_sha256"],
                            "draft": base["report"]["draft"],
                        }
                        if revision
                        else None
                    )
                    # 【文档工具】调用本地 Word 引擎，不调用模型。
                    result = self.documents.render(
                        payload, destination, version_name, allow, previous=previous
                    )
                    if revision:
                        self.reject_noop(result, base, destination)
                    change_kind = "结构修改" if revision else "首次生成"
                    break
                except (ModelServiceError, ImageAssetError):
                    raise
                except (ValueError, KeyError, TypeError) as exc:
                    last_error = exc
                    if isinstance(exc, ModelOutputError):
                        diagnostics = self.settings.data_dir / sid / "diagnostics" / job_id
                        diagnostics.mkdir(parents=True, exist_ok=True)
                        (diagnostics / f"attempt-{attempt + 1}.json").write_text(
                            json.dumps({
                                "attempt": attempt + 1,
                                "error": self.settings.redact(str(exc)),
                                "response_text": self.settings.redact(exc.response_text),
                            }, ensure_ascii=False, indent=2), encoding="utf-8",
                        )
                        if attempt == 2:
                            raise ContentRepairFailure(str(exc)) from None
                        feedback = (
                            equation_feedback if equation_targets is not None
                            else header_feedback if target is not None else messages
                        )
                        if exc.response_text:
                            feedback.append({"role": "assistant", "content": exc.response_text})
                        feedback.append({
                            "role": "user",
                            "content": "上次响应无法解析为完整 JSON。请修复以下具体错误，直接返回符合 schema 的完整 JSON 对象，不附加说明或省略正文。正确转义字符串中的引号、换行和反斜杠；化学富文本使用真正的扁平 run 数组，不把未转义的 JSON 嵌入字符串。保留教师要求与其他内容。错误：" + str(exc),
                        })
                        continue
                    if isinstance(exc, EquationBalanceError):
                        equation_targets = exc.targets
                        equation_feedback = []
                        diagnostics = self.settings.data_dir / sid / "diagnostics" / job_id
                        diagnostics.mkdir(parents=True, exist_ok=True)
                        detail = json.dumps({"attempt": attempt + 1, "error": str(exc),
                                             "equations": equation_targets, "response": raw},
                                            ensure_ascii=False, indent=2)
                        (diagnostics / f"equation-{attempt + 1}.json").write_text(
                            self.settings.redact(detail), encoding="utf-8"
                        )
                    if equation_targets is not None:
                        if attempt == 2:
                            raise ContentRepairFailure(str(exc)) from None
                        if equation_response is not None:
                            equation_feedback.append({"role": "assistant", "content": json.dumps(equation_response, ensure_ascii=False)})
                        equation_feedback.append({"role": "user", "content":
                            "结合上下文修复整个目标方程式，可补齐和更正反应物、生成物、条件及计量数。返回全部目标的 repairs 数组，只替换目标字段，保留其他导学案内容。错误：" + str(exc)})
                        self.stage(job_id, 3, f"自动修复化学方程式（第{attempt + 1}轮）")
                        continue
                    # 【来源规则】缺失真实证据不能靠模型修改声明来通过校验。
                    if getattr(exc, "issues", None) and any(
                        x.get("code") == "MISSING_SOURCES" for x in exc.issues
                    ):
                        raise
                    if attempt == 2:
                        raise ContentRepairFailure(str(last_error)) from None
                    target = target or (
                        header_target(raw) if is_header_error(exc) else None
                    )
                    if target is not None:
                        continue
                    messages.append(
                        {
                            "role": "assistant",
                            "content": json.dumps(
                                locals().get("raw", {}), ensure_ascii=False
                            ),
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "content": "只修复以下错误，保留表格和无关内容："
                            + str(exc),
                        }
                    )
            if result is None:
                raise ValueError(str(last_error))
            if repairs:
                result["format_repairs"] = repairs
                (destination / "generation_report.json").write_text(
                    json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
                    encoding="utf-8",
                )
            self.stage(job_id, 4, "最终方程式校验、Word 装配与结构检查已完成，保存版本")
            content = json.loads((destination / "content.json").read_text())
            version = {
                "id": version_id,
                "number": version_name,
                "parent_id": base["id"] if revision else None,
                "change_kind": change_kind,
                "created_at": now(),
                "content_sha256": result["content_sha256"],
                "content": content,
                "sources": sources,
                "directory": str(destination),
                "report": result,
            }
            # 【状态存储】完整内容与产物就绪后才发布，避免暴露半成品版本。
            self.store.publish(job_id, version)
            published = True
        except Exception as exc:
            if published:
                return
            if destination and destination.exists():
                shutil.rmtree(destination)
            message = self.settings.redact(str(exc))
            # 【错误输出】仅公开可预期的应用错误，其他异常使用通用提示。
            if not isinstance(exc, (ValueError, KeyError, TypeError, OSError)):
                message = "任务执行失败，请检查服务端运行情况后重试"
            detail = (
                self.settings.redact(exc.detail)[:4000]
                if isinstance(exc, ContentRepairFailure)
                else None
            )
            self.store.update_job(
                job_id, status="failed", error=message[:2000], error_detail=detail
            )

import hashlib
import json
import re
import shutil

from .export import export_deck
from .prompting import messages_for, source_context
from .revision import merge_revision
from .store import identity, now


class CoursewarePipeline:
    def __init__(self, settings, store, retriever, model):
        self.settings, self.store, self.retriever, self.model = (
            settings,
            store,
            retriever,
            model,
        )

    def start_generation(self, sid, payload):
        return self.store.reserve(sid, payload, "generation")

    def start_revision(self, sid, payload):
        return self.store.reserve(sid, payload, "revision")

    def run(self, jid):
        directory = None
        try:
            job = self.store.get_job(jid)
            session = job["snapshot"]
            request = job["request"]
            self.store.stage(jid, "检索本课资料")
            settings = session["settings"]
            baseline = session["versions"][-1] if job["kind"] == "revision" else None
            sources = list(baseline["sources"]) if baseline else []
            if (
                self.settings.fastgpt_url
                and self.settings.fastgpt_key
                and self.settings.datasets
            ):
                sources += self.retriever.search(
                    " ".join(
                        settings[k] for k in ("edition", "grade", "chapter", "period")
                    )
                )
            sources += [
                {k: v for k, v in r.items() if k not in ("file_path", "text", "pages")}
                for r in session["resources"]
            ]
            # Keep remote recall flags from claiming teacher verification.
            sources = [
                {**s, "verified": False, "evidence": s.get("evidence", "")}
                for s in sources
            ]
            sources = list(
                {
                    (s["id"], s.get("evidence", ""), s.get("locator", "")): s
                    for s in sources
                }.values()
            )
            previous = (
                session["versions"][-1]["content"]
                if job["kind"] == "revision"
                else None
            )
            messages = messages_for(
                session,
                sources,
                request["prompt"],
                previous,
                request.get("allow_full_revision", False),
            )
            self.store.stage(jid, "设计逐页内容与互动")
            vid = identity()
            directory = (
                self.settings.data_dir / "courseware" / session["id"] / "versions" / vid
            )
            directory.mkdir(parents=True, exist_ok=False)
            result = self.model.generate_json(messages)
            self.store.stage(jid, "装配课件、最终方程式校验与版式检查")
            for attempt in range(3):
                try:
                    candidate = (
                        merge_revision(
                            result,
                            previous,
                            request["prompt"],
                            request.get("allow_full_revision", False),
                        )
                        if previous
                        else result
                    )
                    content, validation = export_deck(candidate, directory, True)
                    break
                except ValueError as exc:
                    if attempt == 2:
                        raise ValueError(
                            "课件内容校验失败，已修复两轮：" + str(exc)
                        ) from None
                    messages.extend(
                        [
                            {
                                "role": "assistant",
                                "content": json.dumps(result, ensure_ascii=False),
                            },
                            {
                                "role": "user",
                                "content": "修复以下结构或版式问题，返回完整 JSON，保留其他内容："
                                + str(exc)[:3000],
                            },
                        ]
                    )
                    result = self.model.generate_json(messages)
            gaps = list(content.get("source_gaps", []))
            if any(s["excerpted"] for s in source_context(sources)):
                gaps.append(
                    "受模型上下文容量限制，长资料按来源均衡节选；完整来源快照保留在引用来源中，请结合原文复核。"
                )
            if not sources:
                gaps.insert(0, "本次未取得可引用资料，请补充教材或教师用书后复核。")
            conflicts = list(content.get("conflicts", []))
            page_request = settings["options"]["pages"]
            match = re.fullmatch(r"(\d+)\s*页?", page_request)
            explicit = re.findall(
                r"(?:总共|总计|总页数\s*[：:]?|设计|生成|课件页数\s*[：:])\s*(\d+)\s*页",
                request["prompt"],
            )
            wanted = int(explicit[-1]) if explicit else int(match[1]) if match else None
            if wanted and wanted != len(content["slides"]):
                conflicts.append(
                    f"要求总页数 {wanted}，实际 {len(content['slides'])} 页（含封面和结束页），请调整内容或页数。"
                )
            report = dict(
                draft=False,
                source_issues=gaps,
                conflicts=conflicts,
                validation=validation,
                visual_review="",
                page_count=len(content["slides"]),
            )
            version = dict(
                id=vid,
                number=f"v{len(session['versions']) + 1:03d}",
                parent_id=previous and session["versions"][-1]["id"],
                created_at=now(),
                content=content,
                sources=sources,
                report=report,
                content_sha256=hashlib.sha256(
                    json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest(),
            )
            (directory / "content.json").write_text(
                json.dumps(content, ensure_ascii=False, indent=2)
            )
            (directory / "generation_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2)
            )
            self.store.finish(jid, version)
        except Exception as exc:
            if directory:
                shutil.rmtree(directory, ignore_errors=True)
            message = (
                self.settings.redact(str(exc))
                if isinstance(exc, ValueError)
                else "课件任务失败，请重试；持续失败请检查服务端日志与连接配置。"
            )
            self.store.fail(jid, message[:4000])

import { useState } from "react";
import { Download, FileCheck, Library, CheckCircle2 } from "lucide-react";
import type { Version, Question, QuestionImage } from "../domain/types";
import { fileUrl, imageUrl } from "../services/api";
import Rich from "./Rich";
import OriginalImage from "../../../components/OriginalImage";
export default function Preview({
  version,
  sessionId,
  onSources,
}: {
  version: Version;
  sessionId: string;
  onSources: () => void;
}) {
  const [answers, setAnswers] = useState(false);
  const p = version.content;
  const pictures = (
    question: Question,
    placement: QuestionImage["placement"],
  ) =>
    (question.images || [])
      .filter((image) => image.placement === placement)
      .map((image, index) => (
        <OriginalImage
          key={`${sessionId}:${version.id}:${placement}:${image.image_id}:${index}`}
          src={imageUrl(sessionId, version.id, image.image_id)}
          caption={image.caption}
        />
      ));
  let number = 0;
  return (
    <article className="document-card">
      <div className="document-toolbar">
        <span>
          <FileCheck size={19} />
          限时练习 · {version.number}
        </span>
        <div>
          <button className="text-button" onClick={onSources}>
            <Library size={16} />
            查看来源
          </button>
          <a
            className="button secondary small"
            href={fileUrl(sessionId, version.id, "paper")}
          >
            <Download size={15} />
            学生卷
          </a>
          <a
            className="button primary small"
            href={fileUrl(sessionId, version.id, "answers")}
          >
            <Download size={15} />
            答案解析卷
          </a>
        </div>
      </div>
      <div className="document-status">
        <span>
          <CheckCircle2 size={14} />
          结构检查通过
        </span>
        <span>
          {p.duration} 分钟 · 满分 {p.total_score} 分 ·{" "}
          {p.choice.length + p.written.length} 道必做题
          {p.optional.length ? ` · ${p.optional.length} 道选做题` : ""}
        </span>
      </div>
      {!!version.report.source_issues.length && (
        <details className="source-issues">
          <summary>
            资料与内容说明（{version.report.source_issues.length}）
          </summary>
          <ul>
            {version.report.source_issues.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </details>
      )}
      <div className="tp-view-switch" aria-label="预览内容">
        <button
          aria-pressed={!answers}
          className={!answers ? "selected" : ""}
          onClick={() => setAnswers(false)}
        >
          学生卷
        </button>
        <button
          aria-pressed={answers}
          className={answers ? "selected" : ""}
          onClick={() => setAnswers(true)}
        >
          答案与解析
        </button>
      </div>
      <div className="tp-paper">
        <h2>
          {p.title}
          {answers ? " · 答案与解析" : ""}
        </h2>
        {!answers && (
          <p className="tp-student">
            姓名 __________　班级 __________　组号 __________
          </p>
        )}
        {(["choice", "written", "optional"] as const).map(
          (group) =>
            p[group].length > 0 && (
              <section key={group}>
                <h3>
                  {group === "choice"
                    ? "一、单项选择题"
                    : group === "written"
                      ? "二、填空及简答题"
                      : "选做题（不计分）"}
                </h3>
                {p[group].map((q) => {
                  const n = ++number;
                  return (
                    <div key={n} className="tp-question">
                      <p>
                        <b>{n}. </b>
                        {q.score > 0 && <span>（{q.score}分）</span>}
                        <Rich value={q.stem} />
                      </p>
                      {pictures(q, "stem")}
                      {!answers && q.options && (
                        <ol className="tp-options">
                          {q.options.map((option, i) => (
                            <li key={i}>
                              <Rich value={option} />
                              {pictures(
                                q,
                                `option_${"ABCD"[i]}` as QuestionImage["placement"],
                              )}
                            </li>
                          ))}
                        </ol>
                      )}
                      {!answers && !q.options && (
                        <div className="tp-work-lines">
                          {Array.from(
                            { length: Math.min(q.work_lines, 5) },
                            (_, i) => (
                              <div key={i} />
                            ),
                          )}
                        </div>
                      )}
                      {answers && (
                        <div className="tp-answer">
                          <p>
                            <b>答案：</b>
                            <Rich value={q.answer} />
                          </p>
                          {pictures(q, "answer")}
                          <p>
                            <b>解析：</b>
                            <Rich value={q.explanation} />
                          </p>
                          {pictures(q, "explanation")}
                          <small>
                            {q.difficulty} · 预估 {q.minutes} 分钟 ·{" "}
                            {q.origin === "original"
                              ? "原题"
                              : q.origin === "adapted"
                                ? "改编题"
                                : "自编题，需教师审核"}
                          </small>
                          <p className="tp-source-note">
                            来源：
                            {q.source_ids
                              .map((id) => {
                                const s = version.sources.find(
                                  (s) => s.id === id,
                                );
                                return s ? `${s.title}（${s.locator}）` : id;
                              })
                              .join("；") || "自编，需教师审核"}
                          </p>
                        </div>
                      )}
                    </div>
                  );
                })}
              </section>
            ),
        )}
      </div>
      <footer className="document-footnote">
        内容预览不代表 Word 分页效果。请结合原题复核答案，并在 Word / WPS
        中检查化学符号和答题空间。
      </footer>
    </article>
  );
}

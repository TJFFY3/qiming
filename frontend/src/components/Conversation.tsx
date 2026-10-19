import { useEffect, useState } from "react";
import {
  Sparkles,
  BadgeCheck,
  Info,
  CheckCircle2,
  LoaderCircle,
  AlertCircle,
  ChevronRight,
  RotateCcw,
  Focus,
} from "lucide-react";
import type { Session, Job, Version } from "../api";
import OutlinePreview from "./OutlinePreview";
export default function Conversation({
  session,
  job,
  version,
  onVersion,
  onSources,
  onVersionSources,
  onRetry,
  onSuggestion,
  busy,
}: {
  session: Session;
  job?: Job;
  version?: Version;
  onVersion: (id: string) => void;
  onSources: () => void;
  onVersionSources: () => void;
  onRetry: () => void;
  onSuggestion: (v: string) => void;
  busy: boolean;
}) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!job) return;
    const tick = () =>
      setElapsed(
        Math.max(
          0,
          Math.floor((Date.now() - new Date(job.created_at).getTime()) / 1000),
        ),
      );
    tick();
    if (job.status === "running" || job.status === "queued") {
      const t = setInterval(tick, 1000);
      return () => clearInterval(t);
    }
  }, [job]);
  const lastRequest = [...session.messages]
    .reverse()
    .find((m) => m.role === "user");
  return (
    <>
      <div className="conversation-content">
        <div className="user-bubble">
          {lastRequest?.content || "请生成一份导学案。"}
          <div className="bubble-meta">
            学科：化学
            <br />
            教材版本：{session.settings.edition}
            <br />
            年级：{session.settings.grade}
            <br />
            章节 / 知识点：{session.settings.chapter}
            <br />
            课时：{session.settings.period}
          </div>
        </div>
        <div className="assistant-row">
          <div className="assistant-avatar">
            <Sparkles size={21} />
          </div>
          <div className="assistant-main">
            <div className="agent-caption">
              <BadgeCheck size={16} />
              启鸣 AI · 化学教学设计<span>基于知识库与教学规范</span>
            </div>
            {job && (
              <div
                className={
                  "progress-card " + (job.status === "failed" ? "failed" : "")
                }
              >
                <div className="progress-header">
                  {job.status === "failed" ? (
                    <AlertCircle size={21} />
                  ) : job.status === "completed" ? (
                    <CheckCircle2 size={21} />
                  ) : (
                    <Info size={21} />
                  )}
                  <div>
                    <strong>
                      {job.status === "failed"
                        ? "生成未完成"
                        : job.status === "completed"
                          ? "导学案已生成"
                          : "正在生成内容"}
                    </strong>
                    <p>
                      已完成{" "}
                      {
                        job.stages.filter((s) => s.status === "completed")
                          .length
                      }{" "}
                      个阶段
                      {busy
                        ? ` · 已用时 ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`
                        : ""}
                    </p>
                  </div>
                </div>
                <div className="stage-list">
                  {job.stages.length ? (
                    job.stages.map((s) => (
                      <div className="stage-row" key={s.index}>
                        {s.status === "completed" ? (
                          <CheckCircle2 size={17} className="success" />
                        ) : job.status === "failed" ? (
                          <AlertCircle size={17} />
                        ) : (
                          <LoaderCircle size={17} className="spin" />
                        )}
                        <span>{s.label}</span>
                        <small>
                          {s.status === "completed"
                            ? "已完成"
                            : job.status === "failed"
                              ? "未完成"
                              : "进行中"}
                        </small>
                        {s.status !== "completed" && <ChevronRight size={16} />}
                      </div>
                    ))
                  ) : (
                    <div className="stage-row">
                      <LoaderCircle size={17} className="spin" />
                      <span>任务已提交，等待开始</span>
                    </div>
                  )}
                </div>
                {job.error && (
                  <div className="task-error">
                    <p>{job.error}</p>
                    <div>
                      <button className="text-button" onClick={onSources}>
                        查看资料
                      </button>
                      <button className="text-button" onClick={onRetry}>
                        <RotateCcw size={14} />
                        重试
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}
            {version && (
              <>
                <div className="version-bar">
                  <span>
                    <Focus size={15} />
                    当前版本 ·{" "}
                    {version.report.draft ? "待核验草案" : "来源已核对"}
                  </span>
                  <select
                    aria-label="选择版本"
                    value={version.id}
                    onChange={(e) => onVersion(e.target.value)}
                  >
                    {session.versions.map((v) => (
                      <option value={v.id} key={v.id}>
                        {v.number} · {v.change_kind}
                      </option>
                    ))}
                  </select>
                </div>
                <OutlinePreview
                  version={version}
                  sessionId={session.id}
                  onSources={onVersionSources}
                />
              </>
            )}
            {!job && !version && (
              <div className="empty-state">
                <Sparkles size={28} />
                <p>输入本课要求，开始生成导学案。</p>
              </div>
            )}
          </div>
        </div>
      </div>
      {!!version && !busy && (
        <div className="suggestions">
          <span>
            <Focus size={14} />
            本次修改：{session.settings.chapter} · {session.settings.period} ·
            基于 {version.number}
          </span>
          <div>
            {["精简情境导入", "增加分层练习", "补充易错提醒"].map((x) => (
              <button key={x} onClick={() => onSuggestion(x)}>
                {x}
              </button>
            ))}
          </div>
        </div>
      )}
    </>
  );
}

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowLeft,
  Library,
  History,
  Plus,
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
export type DetailJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at?: string;
  stages: { label: string; status: string }[];
  error?: string | null;
  error_detail?: string | null;
};
export function ConversationHeader({
  chapter,
  period,
  product,
  onBack,
  onSources,
  onHistory,
  onNew,
  busy = false,
  historyLabel = "历史备课",
  newLabel = "新建备课",
}: {
  chapter: string;
  period: string;
  product: string;
  onBack: () => void;
  onSources: () => void;
  onHistory: () => void;
  onNew: () => void;
  busy?: boolean;
  historyLabel?: string;
  newLabel?: string;
}) {
  return (
    <header className="conversation-header">
      <button className="text-button muted" onClick={onBack}>
        <ArrowLeft size={20} />
        返回备课
      </button>
      <div>
        <h1>
          {chapter} · {period} · {product}
        </h1>
        <p>对话式生成</p>
      </div>
      <div className="conversation-actions">
        <button className="text-button" onClick={onSources}>
          <Library size={18} />
          资料库
        </button>
        <button
          className="icon-button"
          aria-label={historyLabel}
          onClick={onHistory}
        >
          <History size={19} />
        </button>
        <button
          className="button secondary small"
          disabled={busy}
          onClick={onNew}
        >
          <Plus size={16} />
          {newLabel}
        </button>
      </div>
    </header>
  );
}
export function BackgroundTaskNotice({
  product,
  busy,
  sending = false,
  status,
  onResume,
}: {
  product: string;
  busy: boolean;
  sending?: boolean;
  status?: string;
  onResume: () => void;
}) {
  return (
    <div className="active-guide-task" role="status">
      <div>
        {busy ? (
          <LoaderCircle size={19} className="spin" />
        ) : (
          <Focus size={19} />
        )}
        <span>
          <strong>
            {sending
              ? `正在提交${product}任务`
              : busy
                ? `${product}正在后台生成`
                : status === "completed"
                  ? `${product}任务已完成`
                  : `${product}任务未完成`}
          </strong>
          <small>
            {busy
              ? "可切换其他 Agent，任务会继续执行。"
              : "可返回查看任务进度、结果或重试。"}
          </small>
        </span>
      </div>
      <button className="text-button" onClick={onResume}>
        查看任务
        <ChevronRight size={16} />
      </button>
    </div>
  );
}
function TaskProgress({
  job,
  product,
  busy,
  onSources,
  onRetry,
  children,
}: {
  job: DetailJob;
  product: string;
  busy: boolean;
  onSources: () => void;
  onRetry: () => void;
  children?: ReactNode;
}) {
  const [elapsed, setElapsed] = useState(0);
  const started = useRef({ id: "", time: 0 });
  useEffect(() => {
    if (started.current.id !== job.id) {
      const date = Date.parse(job.created_at || "");
      started.current = {
        id: job.id,
        time: Number.isFinite(date) ? date : Date.now(),
      };
    }
    const tick = () =>
      setElapsed(
        Math.max(0, Math.floor((Date.now() - started.current.time) / 1000)),
      );
    tick();
    if (job.status === "queued" || job.status === "running") {
      const timer = setInterval(tick, 1000);
      return () => clearInterval(timer);
    }
  }, [job.id, job.created_at, job.status]);
  return (
    <div
      className={"progress-card " + (job.status === "failed" ? "failed" : "")}
      role="status"
      aria-live="polite"
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
                ? `${product}已生成`
                : "正在生成内容"}
          </strong>
          <p>
            已完成 {job.stages.filter((s) => s.status === "completed").length}{" "}
            个阶段
            {busy
              ? ` · 已用时 ${Math.floor(elapsed / 60)}:${String(elapsed % 60).padStart(2, "0")}`
              : ""}
          </p>
        </div>
      </div>
      <div className="stage-list">
        {job.stages.length ? (
          job.stages.map((s, i) => (
            <div className="stage-row" key={i}>
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
            {job.status === "failed" ? (
              <AlertCircle size={17} />
            ) : job.status === "completed" ? (
              <CheckCircle2 size={17} />
            ) : (
              <LoaderCircle size={17} className="spin" />
            )}
            <span>
              {job.status === "failed"
                ? "任务未完成"
                : job.status === "completed"
                  ? "任务已完成"
                  : "任务已提交，等待开始"}
            </span>
          </div>
        )}
      </div>
      {children}
      {(job.error || job.status === "failed") && (
        <div className="task-error">
          {job.error && <p>{job.error}</p>}
          {job.error_detail && (
            <details className="error-details">
              <summary>查看错误详情</summary>
              <pre>{job.error_detail}</pre>
            </details>
          )}
          <div>
            <button className="text-button" onClick={onSources}>
              查看资料
            </button>
            <button className="text-button" disabled={busy} onClick={onRetry}>
              <RotateCcw size={14} />
              重试
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
export function ConversationView({
  request,
  product,
  job,
  busy,
  onSources,
  onRetry,
  version,
  versions,
  onVersion,
  versionLabel = "选择版本",
  children,
  progressExtra,
}: {
  request: string;
  product: string;
  job?: DetailJob;
  busy: boolean;
  onSources: () => void;
  onRetry: () => void;
  version?: { id: string; number: string };
  versions: { id: string; number: string; label?: string }[];
  onVersion: (id: string) => void;
  versionLabel?: string;
  children?: ReactNode;
  progressExtra?: ReactNode;
}) {
  return (
    <div className="conversation-content">
      <div className="user-bubble">{request}</div>
      <div className="assistant-row">
        <div className="assistant-avatar">
          <Sparkles size={21} />
        </div>
        <div className="assistant-main">
          <div className="agent-caption">
            <BadgeCheck size={16} />
            启鸣 AI · {product === "导学案" ? "化学教学设计" : product}
            <span>基于知识库与教学规范</span>
          </div>
          {job && (
            <TaskProgress
              job={job}
              product={product}
              busy={busy}
              onSources={onSources}
              onRetry={onRetry}
            >
              {progressExtra}
            </TaskProgress>
          )}
          {version && (
            <>
              <div className="version-bar">
                <span>
                  <Focus size={15} />
                  当前版本 · {version.number}
                </span>
                <select
                  aria-label={versionLabel}
                  value={version.id}
                  onChange={(e) => onVersion(e.target.value)}
                >
                  {versions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.number}
                      {v.label ? ` · ${v.label}` : ""}
                    </option>
                  ))}
                </select>
              </div>
              {version.id !== versions.at(-1)?.id && (
                <p className="historical-version-note">
                  历史版本仅供查看，切换最新版本后可继续修改
                </p>
              )}
              {children}
            </>
          )}
          {!job && !version && (
            <div className="empty-state">
              <Sparkles size={28} />
              <p>输入本课要求，开始生成{product}。</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
export function RevisionSuggestions({
  chapter,
  period,
  version,
  items,
  onSuggestion,
  disabled = false,
}: {
  chapter: string;
  period: string;
  version: string;
  items: string[];
  onSuggestion: (text: string) => void;
  disabled?: boolean;
}) {
  return (
    <div className="suggestions">
      <span>
        <Focus size={14} />
        本次修改：{chapter} · {period} · 基于 {version}
      </span>
      <div>
        {items.map((text) => (
          <button
            key={text}
            disabled={disabled}
            onClick={() => onSuggestion(text)}
          >
            {text}
          </button>
        ))}
      </div>
    </div>
  );
}
export function ConversationComposer({
  children,
}: {
  children: ReactNode;
}) {
  return <div className="chat-composer-wrap">{children}</div>;
}

import { createPortal } from "react-dom";
import { useWorkbench, WorkbenchPreview } from "./AgentWorkbench";
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
  ended_at?: string;
  updated_at?: string;
  duration_seconds?: number;
  stages: { label: string; status: string; started_at?: string; ended_at?: string; duration_seconds?: number }[];
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
  const workbench = useWorkbench();
  const header = (
    <header className="conversation-header">
      <button className="icon-button" aria-label="返回备课" title="返回备课" onClick={() => { workbench?.showChat(); onBack(); }}><ArrowLeft size={20} /></button>
      <div>
        <h1 title={`${chapter} · ${period} · ${product}`}>
          {chapter} · {period} · {product}
        </h1>
      </div>
      <div className="conversation-actions">
        {!workbench && <>
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
        </>}
        {!workbench && <button
          className="button secondary small"
          disabled={busy}
          onClick={onNew}
        >
          <Plus size={16} />
          {newLabel}
        </button>}
      </div>
    </header>
  );
  if (!workbench) return header;
  return workbench.headerTarget ? createPortal(header, workbench.headerTarget) : null;
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
function elapsedSeconds(start?: string, end?: string | number, recorded?: number) {
  if (recorded !== undefined && Number.isFinite(recorded)) return Math.max(0, recorded);
  const from = Date.parse(start || "");
  const to = typeof end === "number" ? end : Date.parse(end || "");
  return Number.isFinite(from) && Number.isFinite(to) ? Math.max(0, (to-from)/1000) : null;
}
function formatElapsed(seconds: number | null) {
  if (seconds === null) return "未记录";
  if (seconds < 1) return "<1秒";
  const value = Math.floor(seconds);
  return value < 60 ? `${value}秒` : `${Math.floor(value/60)}分${value%60}秒`;
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
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    setClock(Date.now());
    if (job.status !== "queued" && job.status !== "running") return;
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [job.id, job.status]);
  const running = job.status === "queued" || job.status === "running";
  const elapsed = elapsedSeconds(job.created_at, running ? clock : job.ended_at || job.updated_at, running ? undefined : job.duration_seconds);
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
            {running ? ` · 已用时 ${formatElapsed(elapsed)}` : ""}
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
              <small className="stage-duration">{formatElapsed(elapsedSeconds(s.started_at, s.ended_at || (running && s.status === "running" ? clock : undefined), s.duration_seconds))}</small>
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
      {!running && <p className="task-total-duration">总耗时 {formatElapsed(elapsed)}</p>}
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
  messages,
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
  messages?: { role: string; content: string }[];
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
  const workbench = useWorkbench();
  const latestTurn = useRef<HTMLDivElement>(null);
  useEffect(() => {
    latestTurn.current?.scrollIntoView?.({ block: "end" });
  }, [messages?.length, job?.id]);
  const progress = (<>
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
  </>);
  const preview = (<>
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
  </>);
  return (
    <div className="conversation-content">
      <div className="conversation-transcript" aria-label="对话记录">
        {(messages?.filter((m) => m.role === "user" || m.role === "assistant").length
          ? messages.filter((m) => m.role === "user" || m.role === "assistant")
          : [{ role: "user", content: request }]).map((message, index) => (
          <div key={index} className={message.role === "user" ? "user-bubble" : "assistant-message"}>
            {message.role === "assistant" && <small>启鸣 AI</small>}
            <div>{message.content}</div>
          </div>
        ))}
      </div>
      <div className="assistant-row">
        <div className="assistant-avatar">
          <Sparkles size={21} />
        </div>
        <div className="assistant-main">
          <div className="agent-caption">
            <BadgeCheck size={16} />
            Fast AI· {product === "导学案" ? "教学设计" : product}
            <span>基于知识库与教学规范</span>
          </div>
          {workbench ? (
            <>
              {progress}
              <div className="workbench-task-reply">
                <p>{busy ? `正在处理你的${product}任务，执行进度会在此更新。` : job?.status === "failed" ? "本次任务未完成，可查看下方详情并重试。" : version ? `${product}文件已准备好，可在右侧预览、下载或继续修改。` : `描述本课要求，开始生成${product}。`}</p>
                <button className="text-button" onClick={workbench.showPreview}><Focus size={15} />在右侧查看文件<ChevronRight size={15} /></button>
              </div>
              <WorkbenchPreview>{preview}</WorkbenchPreview>
            </>
          ) : <>{progress}{preview}</>}
        </div>
      </div>
      <div ref={latestTurn} className="conversation-latest-turn" />
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

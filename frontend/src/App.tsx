import { useCallback, useEffect, useState, useRef } from "react";
import {
  Sparkles,
  FileText,
  Presentation,
  ListChecks,
  Library,
  Paperclip,
  ArrowLeft,
  History,
  X,
  Plus,
  AlertCircle,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import {
  api,
  post,
  defaultSettings,
  type Settings,
  type Options,
  type Session,
  type SessionSummary,
  type Job,
  type Source,
} from "./api";
import Composer from "./components/Composer";
import OptimizeDialog from "./components/OptimizeDialog";
import Conversation from "./components/Conversation";
import Resources from "./components/Resources";
import Modal from "./components/Modal";
export default function App() {
  const [settings, setSettings] = useState<Settings>(defaultSettings),
    [session, setSession] = useState<Session | null>(null),
    [prompt, setPrompt] = useState("");
  const [page, setPage] = useState<"home" | "conversation">("home"),
    [modal, setModal] = useState<
      "optimize" | "resources" | "history" | "versionSources" | null
    >(null),
    [error, setError] = useState("");
  const [health, setHealth] = useState<{
      ready: boolean;
      missing: string[];
    } | null>(null),
    [sending, setSending] = useState(false),
    [job, setJob] = useState<Job>(),
    [versionId, setVersionId] = useState(""),
    [allowDraft, setAllowDraft] = useState(false),
    [history, setHistory] = useState<SessionSummary[]>([]),
    [notice, setNotice] = useState("");
  const requestRef = useRef(false);
  const busy = sending || job?.status === "running" || job?.status === "queued";
  const version =
    session?.versions.find((v) => v.id === versionId) ||
    session?.versions.at(-1);
  const closeModal = useCallback(() => setModal(null), []);
  useEffect(() => {
    api<{ ready: boolean; missing: string[] }>("/health")
      .then(setHealth)
      .catch((e) => setError(e.message));
    const id = localStorage.getItem("qiming-session");
    if (id)
      api<Session>("/sessions/" + id)
        .then((s) => {
          setSession(s);
          setSettings(s.settings);
          const j = s.jobs.at(-1);
          setJob(j);
          if (s.versions.length || j) setPage("conversation");
        })
        .catch(() => localStorage.removeItem("qiming-session"));
  }, []);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const latest = await api<Job>("/jobs/" + job.id);
        if (cancelled) return;
        if (latest.status === "completed" || latest.status === "failed") {
          const s = await api<Session>("/sessions/" + latest.session_id);
          if (!cancelled) {
            setSession(s);
            if (latest.version_id) setVersionId(latest.version_id);
            setJob(latest);
          }
          return;
        }
        setJob(latest);
        timer = setTimeout(poll, 1100);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          timer = setTimeout(poll, 3000);
        }
      }
    };
    timer = setTimeout(poll, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timer);
  }, [notice]);
  const ensureSession = async () => {
    if (session) return session;
    const s = await post<Session>("/sessions", settings);
    setSession(s);
    localStorage.setItem("qiming-session", s.id);
    return s;
  };
  const syncSettings = async (s: Session) => {
    await api("/sessions/" + s.id, {
      method: "PATCH",
      body: JSON.stringify(settings),
    });
  };
  const submit = async (
    suggestion?: string,
    operation?: "generation" | "revision",
    baseId?: string,
  ) => {
    if (requestRef.current || busy) return;
    if (!settings.chapter.trim()) {
      setError("请填写章节 / 知识点");
      return;
    }
    const instruction =
      suggestion || prompt.trim() || "请根据本课内容生成一份导学案。";
    if (
      page === "conversation" &&
      version &&
      session?.versions.at(-1)?.id !== version.id
    ) {
      setError("请切换至最新版本后修改，历史版本保留供查看。");
      return;
    }
    requestRef.current = true;
    setSending(true);
    setError("");
    try {
      const s = await ensureSession();
      await syncSettings(s);
      const isRevision = operation
        ? operation === "revision"
        : page === "conversation" && !!version;
      const j = await post<Job>(
        `/sessions/${s.id}/${isRevision ? "revise" : "generate"}`,
        isRevision
          ? { prompt: instruction, base_version_id: baseId || version?.id }
          : { prompt: instruction, allow_draft: allowDraft },
      );
      setJob(j);
      setPage("conversation");
      setPrompt("");
      setSession(await api<Session>("/sessions/" + s.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
      requestRef.current = false;
    }
  };
  const openHistory = async () => {
    setModal("history");
    try {
      setHistory(await api<SessionSummary[]>("/sessions"));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const loadSession = async (id: string) => {
    try {
      const s = await api<Session>("/sessions/" + id);
      setSession(s);
      setSettings(s.settings);
      setJob(s.jobs.at(-1));
      setVersionId(s.versions.at(-1)?.id || "");
      setPage(s.jobs.length ? "conversation" : "home");
      setModal(null);
      setPrompt("");
      setError("");
      localStorage.setItem("qiming-session", id);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const upload = async (file: File, category: string) => {
    const s = await ensureSession();
    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    await api(`/sessions/${s.id}/resources`, { method: "POST", body: form });
    setSession(await api<Session>("/sessions/" + s.id));
  };
  const review = async (source: Source, note: string, verified: boolean) => {
    if (!session) return;
    setSession(
      await post<Session>(
        `/sessions/${session.id}/sources/${source.id}/review`,
        { note, verified },
      ),
    );
  };
  const newSession = () => {
    if (busy) {
      setNotice("当前任务仍在执行，请完成后新建备课。");
      return;
    }
    setSession(null);
    setJob(undefined);
    setVersionId("");
    setPage("home");
    setPrompt("");
    setSettings(defaultSettings());
    localStorage.removeItem("qiming-session");
    setError("");
  };
  const apply = (options: Options) => {
    setSettings((old) => ({ ...old, options }));
    setModal(null);
    setNotice("优化要求已填入，本次生成时生效");
  };
  const optimized =
    JSON.stringify(settings.options) !==
    JSON.stringify(defaultSettings().options);
  const retry = () =>
    void submit(
      session?.messages.filter((m) => m.role === "user").at(-1)?.content,
      job?.kind || "generation",
      job?.base_version_id || undefined,
    );
  return (
    <div
      className={"app " + (page === "conversation" ? "conversation-page" : "")}
    >
      {page === "home" ? (
        <header className="site-header">
          <button className="brand" onClick={newSession}>
            <span className="brand-mark">
              <Sparkles size={20} />
            </span>
            启鸣
            <span className="brand-divider" />
            教学工作台
          </button>
          <div className="header-actions">
            <span className="connection">
              <i className={health?.ready ? "online" : ""} />
              {health?.ready ? "服务已连接" : "本地工作台"}
            </span>
            <button
              className="icon-button"
              aria-label="历史备课"
              onClick={() => void openHistory()}
            >
              <History size={19} />
            </button>
          </div>
        </header>
      ) : (
        <header className="conversation-header">
          <button className="text-button muted" onClick={() => setPage("home")}>
            <ArrowLeft size={20} />
            返回备课
          </button>
          <div>
            <h1>
              {settings.chapter} · {settings.period} · 导学案
            </h1>
            <p>对话式生成</p>
          </div>
          <div className="conversation-actions">
            <button
              className="text-button"
              onClick={() => setModal("resources")}
            >
              <Library size={18} />
              资料库
            </button>
            <button
              className="icon-button"
              aria-label="历史备课"
              onClick={() => void openHistory()}
            >
              <History size={19} />
            </button>
            <button className="button secondary small" onClick={newSession}>
              <Plus size={16} />
              新建备课
            </button>
          </div>
        </header>
      )}
      {error && (
        <div role="alert" className="error-banner">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button
            className="icon-button"
            aria-label="关闭错误"
            onClick={() => setError("")}
          >
            <X size={17} />
          </button>
        </div>
      )}
      {page === "home" ? (
        <main className="home-main">
          <section className="hero">
            <div className="eyebrow">
              <span />
              让每一节课，都有好设计
            </div>
            <h1>
              <span>启鸣 AI</span>，帮你备课
            </h1>
            <div className="product-tabs" role="tablist" aria-label="备课产物">
              <button role="tab" aria-selected="true" className="active">
                <FileText size={22} />
                导学案
              </button>
              <button
                role="tab"
                aria-selected="false"
                onClick={() => setNotice("互动课件将在后续版本开放")}
              >
                <Presentation size={23} />
                互动课件
              </button>
              <button
                role="tab"
                aria-selected="false"
                onClick={() => setNotice("限时练习将在后续版本开放")}
              >
                <ListChecks size={23} />
                限时练习
              </button>
            </div>
          </section>
          <section className="workspace">
            <div className="resource-toolbar">
              <div>
                <button
                  className="text-button library-button"
                  onClick={() => setModal("resources")}
                >
                  <Library size={20} />
                  资料库
                  {session &&
                    session.sources.length + session.resources.length > 0 && (
                      <b>
                        {
                          new Set(
                            [...session.sources, ...session.resources].map(
                              (s) => s.id,
                            ),
                          ).size
                        }
                      </b>
                    )}
                </button>
                <button
                  className="text-button"
                  onClick={() => setModal("resources")}
                >
                  <Paperclip size={20} />
                  上传资源
                </button>
              </div>
              <div className="lesson-context">
                <input
                  aria-label="教材版本"
                  maxLength={200}
                  value={settings.edition}
                  onChange={(e) =>
                    setSettings({ ...settings, edition: e.target.value })
                  }
                />
                <span>·</span>
                <select
                  aria-label="年级"
                  value={settings.grade}
                  onChange={(e) =>
                    setSettings({ ...settings, grade: e.target.value })
                  }
                >
                  <option>高一</option>
                  <option>高二</option>
                  <option>高三</option>
                </select>
              </div>
            </div>
            <Composer
              settings={settings}
              onSettings={setSettings}
              prompt={prompt}
              onPrompt={setPrompt}
              onSubmit={() => void submit()}
              onOptimize={() => setModal("optimize")}
              onHistory={() => void openHistory()}
              busy={busy}
            />
            <div className="workspace-bottom">
              <label className="draft-option">
                <input
                  type="checkbox"
                  checked={allowDraft}
                  onChange={(e) => setAllowDraft(e.target.checked)}
                />
                允许生成待核验草案
                <span title="来源尚未核对时，生成的文档会明确标记待核验">
                  ⓘ
                </span>
              </label>
              {optimized ? (
                <button
                  className="applied-options"
                  onClick={() => setModal("optimize")}
                >
                  <SlidersIcon />
                  已填入优化要求
                  <ChevronRight size={13} />
                </button>
              ) : (
                <span>从本课教材出发，生成可编辑的导学案</span>
              )}
            </div>
          </section>
          <footer className="home-footer">
            <span className="footer-line" />
            <Sparkles size={14} />
            <span>把备课的时间，还给教学的思考</span>
            <span className="footer-line" />
          </footer>
        </main>
      ) : (
        <main className="chat-main">
          {session && (
            <Conversation
              session={session}
              job={job}
              version={version}
              onVersion={setVersionId}
              onSources={() => setModal("resources")}
              onVersionSources={() => setModal("versionSources")}
              onRetry={retry}
              onSuggestion={(s) => void submit(s)}
              busy={busy}
            />
          )}
          <div className="chat-composer-wrap">
            {!version && (
              <label className="draft-option">
                <input
                  type="checkbox"
                  checked={allowDraft}
                  disabled={busy}
                  onChange={(e) => setAllowDraft(e.target.checked)}
                />
                允许生成待核验草案
              </label>
            )}
            <Composer
              conversation
              settings={settings}
              onSettings={setSettings}
              prompt={prompt}
              onPrompt={setPrompt}
              onSubmit={() => void submit()}
              onOptimize={() => setModal("optimize")}
              onHistory={() => void openHistory()}
              busy={busy}
            />
            <p className="chat-disclaimer">
              内容由 AI 辅助生成，请结合教材与学情复核后使用。
            </p>
          </div>
        </main>
      )}
      {notice && (
        <div className="toast" role="status">
          <Sparkles size={17} />
          {notice}
        </div>
      )}
      {modal === "optimize" && (
        <OptimizeDialog
          chapter={settings.chapter}
          value={settings.options}
          onApply={apply}
          onClose={closeModal}
        />
      )}
      {modal === "resources" && (
        <Resources
          sources={session?.sources || []}
          resources={session?.resources || []}
          onUpload={upload}
          onReview={review}
          onClose={closeModal}
          busy={busy}
        />
      )}
      {modal === "versionSources" && version && (
        <Resources
          snapshot
          sources={version.sources || []}
          resources={[]}
          sourceIssues={version.report.source_issues || []}
          onUpload={upload}
          onReview={review}
          onClose={closeModal}
          busy={busy}
        />
      )}
      {modal === "history" && (
        <Modal title="历史备课" onClose={closeModal} className="history-modal">
          <div className="modal-scroll">
            {history.length ? (
              history.map((s) => (
                <button
                  className="history-item"
                  key={s.id}
                  onClick={() => void loadSession(s.id)}
                >
                  <span className="history-icon">
                    <FileText size={21} />
                  </span>
                  <div>
                    <strong>{s.settings.chapter}</strong>
                    <p>
                      {s.settings.period} · {s.version_count} 个版本 ·{" "}
                      {new Date(s.updated_at).toLocaleString("zh-CN", {
                        timeZone: "Asia/Shanghai",
                      })}
                    </p>
                  </div>
                  <ChevronRight size={18} />
                </button>
              ))
            ) : (
              <div className="empty-state">
                <History size={32} />
                <h3>还没有历史备课</h3>
                <p>开始准备你的第一份导学案吧。</p>
              </div>
            )}
          </div>
        </Modal>
      )}
      {sending && (
        <div className="sending-indicator" aria-live="polite">
          <LoaderCircle size={16} className="spin" />
          正在提交…
        </div>
      )}
    </div>
  );
}
function SlidersIcon() {
  return <span aria-hidden="true">✦</span>;
}

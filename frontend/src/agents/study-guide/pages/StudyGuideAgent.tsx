/** 【界面编排】导学案独立页面：会话、任务轮询、资料与版本交互。 */
import { useCallback, useEffect, useState, useRef } from "react";
import {
  Sparkles,
  FileText,
  Library,
  History,
  ChevronRight,
  X,
  AlertCircle,
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
} from "../services/api";
import { applyOptimization, formatLessonPrompt } from "../domain/prompt";
import Composer from "../../../components/Composer";
import OptimizeDialog from "../components/OptimizeDialog";
import Conversation from "../components/Conversation";
import Resources from "../../../components/Resources";
import Modal from "../../../components/Modal";
import {
  AgentHomeHeader,
  AgentHero,
  LessonToolbar,
  AgentHomeFooter,
  AppliedOptions,
} from "../../../components/AgentHome";
import {
  ConversationHeader,
  ConversationComposer,
  BackgroundTaskNotice,
} from "../../../components/AgentConversation";

export default function StudyGuideAgent({
  onCourseware,
  onPractice,
}: {
  onCourseware: () => void;
  onPractice: () => void;
}) {
  // 【页面状态】备课设置、会话与输入草稿由导学案页面独立维护。
  const [settings, setSettings] = useState<Settings>(defaultSettings),
    [session, setSession] = useState<Session | null>(null),
    [prompt, setPrompt] = useState("");
  const [page, setPage] = useState<"home" | "conversation">("home"),
    [modal, setModal] = useState<
      "optimize" | "resources" | "recall" | "history" | "versionSources" | null
    >(null),
    [error, setError] = useState("");
  const [health, setHealth] = useState<{
      ready: boolean;
      missing: string[];
    } | null>(null),
    [sending, setSending] = useState(false),
    [job, setJob] = useState<Job>(),
    [versionId, setVersionId] = useState(""),
    [history, setHistory] = useState<SessionSummary[]>([]),
    [notice, setNotice] = useState("");
  const requestRef = useRef(false);
  const returnHomeRef = useRef(false);
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
          setSettings({
            ...s.settings,
            period: s.settings.period === "第二课时" ? "第二课时" : "第一课时",
          });
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
  // 【会话接口】按需创建后端会话，生成与修订共用当前会话。
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
  // 【任务提交】提交后由后端编排模型、规则与文档工具；页面负责展示进度。
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
    const instruction = formatLessonPrompt(
      suggestion || prompt.trim() || "请根据本课内容生成一份导学案。",
      settings,
    );
    if (instruction.length > 8000) {
      setError("提示词超过8000字，请精简补充要求或备课内容。");
      return;
    }
    if (
      page === "conversation" &&
      version &&
      session?.versions.at(-1)?.id !== version.id
    ) {
      setError("请切换至最新版本后修改，历史版本保留供查看。");
      return;
    }
    requestRef.current = true;
    returnHomeRef.current = false;
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
          : { prompt: instruction },
      );
      setJob(j);
      if (!returnHomeRef.current) setPage("conversation");
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
      setSettings({
        ...s.settings,
        period: s.settings.period === "第二课时" ? "第二课时" : "第一课时",
      });
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
  // 【资料接口】上传本课资料，由后端提取文本并纳入后续来源。
  const upload = async (file: File, category: string) => {
    const s = await ensureSession();
    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    await api(`/sessions/${s.id}/resources`, { method: "POST", body: form });
    setSession(await api<Session>("/sessions/" + s.id));
  };
  const deleteResource = async (resourceId: string) => {
    if (!session) return;
    setSession(
      await api<Session>(`/sessions/${session.id}/resources/${resourceId}`, {
        method: "DELETE",
      }),
    );
    setNotice("已删除本课资料，后续生成不再使用；历史版本保留原来源。");
  };
  const resetDraft = (preserveLesson = false) => {
    if (busy) {
      setNotice("当前任务仍在执行，请完成后新建备课。");
      return;
    }
    setSession(null);
    returnHomeRef.current = false;
    setJob(undefined);
    setVersionId("");
    setPage("home");
    setPrompt("");
    setSettings((old) =>
      preserveLesson
        ? { ...old, options: defaultSettings().options }
        : defaultSettings(),
    );
    setModal(null);
    setNotice("");
    localStorage.removeItem("qiming-session");
    setError("");
  };
  const newSession = () => resetDraft();
  const returnHome = () => {
    if (busy) {
      // Navigation must not reset the active session or stop its polling.
      returnHomeRef.current = true;
      setPage("home");
      setModal(null);
      setError("");
    } else {
      resetDraft(true);
    }
  };
  const apply = (options: Options) => {
    setSettings((old) => ({ ...old, options }));
    setPrompt((old) =>
      formatLessonPrompt(
        applyOptimization(
          old.trim() ||
            (page === "conversation" && version
              ? "请按以下优化要求调整当前导学案，保留未涉及内容。"
              : "请根据本课内容生成一份导学案。"),
          options,
        ),
        { ...settings, options },
      ),
    );
    setModal(null);
    setNotice("优化要求已写入提示词，可查看和编辑后提交");
  };
  const optimized =
    JSON.stringify(settings.options) !==
    JSON.stringify(defaultSettings().options);
  const retry = () =>
    void submit(
      prompt.trim() ||
        session?.messages.filter((m) => m.role === "user").at(-1)?.content,
      job?.kind || "generation",
      job?.base_version_id || undefined,
    );
  return (
    <div
      className={"app " + (page === "conversation" ? "conversation-page" : "")}
    >
      {page === "home" ? (
        <AgentHomeHeader
          ready={!!health?.ready}
          onNew={newSession}
          onHistory={() => void openHistory()}
        />
      ) : (
        <ConversationHeader
          chapter={settings.chapter}
          period={settings.period}
          product="导学案"
          onBack={returnHome}
          onSources={() => setModal("resources")}
          onHistory={() => void openHistory()}
          onNew={newSession}
          busy={busy}
        />
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
          <AgentHero
            active="guide"
            onChange={(kind) => {
              if (kind === "courseware") onCourseware();
              else if (kind === "practice") onPractice();
            }}
          />
          <section className="workspace">
            {session && (job || sending) && (
              <BackgroundTaskNotice
                product="导学案"
                busy={busy}
                sending={sending}
                status={job?.status}
                onResume={() => {
                  returnHomeRef.current = false;
                  setPage("conversation");
                }}
              />
            )}
            <LessonToolbar
              settings={settings}
              onSettings={setSettings}
              onResources={() => setModal("resources")}
              busy={busy}
              uploadCount={session?.resources.length || 0}
            />
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
            <AppliedOptions
              optimized={optimized}
              onOptimize={() => setModal("optimize")}
              hint="从本课教材出发，生成可编辑的导学案"
            />
          </section>
          <AgentHomeFooter />
        </main>
      ) : (
        <main className="chat-main">
          {session && session.sources.length > 0 && (
            <button
              className="text-button agent-source-review"
              onClick={() => setModal("recall")}
            >
              <Library size={16} /> 本课引用来源（{session.sources.length}）
            </button>
          )}
          {session && (
            <Conversation
              session={session}
              job={job}
              version={version}
              onVersion={setVersionId}
              onSources={() => setModal("recall")}
              onVersionSources={() => setModal("versionSources")}
              onRetry={retry}
              onSuggestion={(s) => void submit(s)}
              busy={busy}
            />
          )}
          <ConversationComposer>
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
          </ConversationComposer>
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
      {(modal === "resources" || modal === "recall") && (
        <Resources
          recall={modal === "recall"}
          onDelete={deleteResource}
          sources={session?.sources || []}
          resources={session?.resources || []}
          onUpload={upload}
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

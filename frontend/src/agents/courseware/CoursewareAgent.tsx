import { useCallback, useEffect, useRef, useState } from "react";
import { AlertCircle, Library, Presentation, Sparkles, X } from "lucide-react";
import Modal from "../../components/Modal";
import { CoursewareApiError, post, request } from "./api";
import {
  defaultSettings,
  type CoursewareOptions,
  type CoursewareSettings,
  type Job,
  type Session,
  type SessionSummary,
} from "./types";
import { applyOptimization } from "./prompt";
import Composer from "./Composer";
import OptimizeDialog from "./OptimizeDialog";
import Preview from "./Preview";
import Resources from "./Resources";
import "./courseware.css";
import {
  AgentHomeHeader,
  AgentHero,
  LessonToolbar,
  AgentHomeFooter,
  AppliedOptions,
} from "../../components/AgentHome";
import {
  ConversationHeader,
  ConversationView,
  ConversationComposer,
  RevisionSuggestions,
  BackgroundTaskNotice,
} from "../../components/AgentConversation";
const SESSION_KEY = "qiming-courseware-session",
  DRAFT_KEY = "qiming-courseware-draft";
function initialDraft(): {
  settings: CoursewareSettings;
  prompt: string;
  allowFullRevision: boolean;
  sessionId: string | null;
} {
  try {
    const raw = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (raw && typeof raw.prompt === "string" && raw.settings?.options)
      return {
        settings: {
          ...defaultSettings(),
          ...raw.settings,
          options: { ...defaultSettings().options, ...raw.settings.options },
        },
        prompt: raw.prompt,
        allowFullRevision: raw.allowFullRevision === true,
        sessionId: typeof raw.sessionId === "string" ? raw.sessionId : null,
      };
  } catch {
    /* Use an empty draft if browser storage is invalid. */
  }
  return {
    settings: defaultSettings(),
    prompt: "",
    allowFullRevision: false,
    sessionId: null,
  };
}
export default function CoursewareAgent({
  onGuide,
  onPractice,
}: {
  onGuide: () => void;
  onPractice?: () => void;
}) {
  const [initial] = useState(initialDraft),
    [settings, setSettings] = useState(initial.settings),
    [prompt, setPrompt] = useState(initial.prompt),
    [allowFullRevision, setAllowFullRevision] = useState(
      initial.allowFullRevision,
    );
  const [session, setSession] = useState<Session | null>(null),
    [job, setJob] = useState<Job>(),
    [versionId, setVersionId] = useState(""),
    [page, setPage] = useState<"home" | "conversation">("home");
  const [modal, setModal] = useState<
      "optimize" | "resources" | "sources" | "history" | null
    >(null),
    [history, setHistory] = useState<SessionSummary[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [sending, setSending] = useState(false),
    [ready, setReady] = useState(false),
    [restoring, setRestoring] = useState(true);
  const locked = useRef(false),
    creating = useRef<Promise<Session> | null>(null),
    sessionRef = useRef<Session | null>(null);
  const busy =
    restoring ||
    sending ||
    job?.status === "queued" ||
    job?.status === "running";
  const version =
    session?.versions.find((v) => v.id === versionId) ||
    session?.versions.at(-1);
  const close = useCallback(() => setModal(null), []);
  const remember = (value: Session) => {
    sessionRef.current = value;
    setSession(value);
    localStorage.setItem(SESSION_KEY, value.id);
  };
  useEffect(() => {
    let active = true;
    void request<{ ready: boolean }>("/health")
      .then((h) => {
        if (active) setReady(h.ready);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    const sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
      setRestoring(false);
      return () => {
        active = false;
      };
    }
    void request<Session>("/sessions/" + sid)
      .then((s) => {
        if (!active) return;
        remember(s);
        if (initial.sessionId !== sid) setSettings(s.settings);
        setJob(s.jobs.at(-1));
        if (s.jobs.length || s.versions.length) setPage("conversation");
      })
      .catch((e) => {
        if (active) {
          setError(e.message);
          if (e instanceof CoursewareApiError && e.status === 404)
            localStorage.removeItem(SESSION_KEY);
        }
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!restoring)
      localStorage.setItem(
        DRAFT_KEY,
        JSON.stringify({
          settings,
          prompt,
          allowFullRevision,
          sessionId: session?.id || localStorage.getItem(SESSION_KEY),
        }),
      );
  }, [settings, prompt, allowFullRevision, restoring, session?.id]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const latest = await request<Job>("/jobs/" + job.id);
        if (!active) return;
        if (latest.status === "completed" || latest.status === "failed") {
          const s = await request<Session>("/sessions/" + latest.session_id);
          if (!active) return;
          remember(s);
          setVersionId(latest.version_id || "");
          setJob(latest);
          return;
        }
        setJob(latest);
        timer = setTimeout(poll, 1100);
      } catch (e) {
        if (active) {
          setError((e as Error).message);
          timer = setTimeout(poll, 3000);
        }
      }
    };
    timer = setTimeout(poll, 500);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);
  const ensureSession = async () => {
    if (sessionRef.current) return sessionRef.current;
    if (!creating.current) {
      const existingId = localStorage.getItem(SESSION_KEY);
      creating.current = (
        existingId
          ? request<Session>("/sessions/" + existingId)
          : post<Session>("/sessions", settings)
      )
        .then((s) => {
          remember(s);
          return s;
        })
        .finally(() => {
          creating.current = null;
        });
    }
    return creating.current;
  };
  const returnHomeRef = useRef(false);
  const submit = async (retry = false, suggestion?: string) => {
    if (locked.current || busy || restoring) return;
    if (
      page === "conversation" &&
      version &&
      version.id !== session?.versions.at(-1)?.id
    ) {
      setError("请切换到最新课件版本后修改。");
      return;
    }
    const text =
      suggestion ||
      prompt.trim() ||
      (retry
        ? session?.messages.filter((m) => m.role === "user").at(-1)?.content
        : "") ||
      "请根据本课内容生成互动课件。";
    returnHomeRef.current = false;
    locked.current = true;
    setSending(true);
    setError("");
    try {
      const s = await ensureSession();
      await request("/sessions/" + s.id, {
        method: "PATCH",
        body: JSON.stringify(settings),
      });
      const revise = retry
        ? job?.kind === "revision"
        : page === "conversation" && !!version;
      const next = await post<Job>(
        `/sessions/${s.id}/${revise ? "revise" : "generate"}`,
        {
          prompt: text,
          allow_draft: true,
          ...(revise
            ? {
                base_version_id: session?.versions.at(-1)?.id,
                allow_full_revision: allowFullRevision,
              }
            : {}),
        },
      );
      setJob(next);
      if (!returnHomeRef.current) setPage("conversation");
      setPrompt("");
      remember(await request<Session>("/sessions/" + s.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      locked.current = false;
      setSending(false);
    }
  };
  const openHistory = async () => {
    setModal("history");
    setError("");
    try {
      setHistory(await request<SessionSummary[]>("/sessions"));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const load = async (id: string) => {
    if (busy) {
      setNotice("当前课件任务仍在执行，请完成后切换会话。");
      return;
    }
    try {
      const s = await request<Session>("/sessions/" + id);
      remember(s);
      setSettings(s.settings);
      setJob(s.jobs.at(-1));
      setVersionId(s.versions.at(-1)?.id || "");
      setPage(s.jobs.length ? "conversation" : "home");
      setPrompt("");
      setModal(null);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const resetSession = (preserveLesson: boolean) => {
    if (busy) {
      setNotice("当前课件任务仍在执行，请完成后新建。");
      return;
    }
    returnHomeRef.current = false;
    sessionRef.current = null;
    setSession(null);
    setJob(undefined);
    setVersionId("");
    setPage("home");
    setPrompt("");
    setSettings((old) =>
      preserveLesson
        ? { ...old, options: defaultSettings().options }
        : defaultSettings(),
    );
    setAllowFullRevision(false);
    setError("");
    setModal(null);
    localStorage.removeItem(SESSION_KEY);
  };
  const newSession = () => resetSession(false);
  const apply = (options: CoursewareOptions) => {
    setSettings((old) => ({ ...old, options }));
    setPrompt((old) => applyOptimization(old, options));
    setModal(null);
    setNotice("课件优化要求已填入，可编辑后提交。");
  };
  const upload = async (file: File, category: string) => {
    const s = await ensureSession();
    const body = new FormData();
    body.append("file", file);
    body.append("category", category);
    await request(`/sessions/${s.id}/resources`, { method: "POST", body });
    remember(await request<Session>("/sessions/" + s.id));
  };
  const deleteResource = async (id: string) => {
    if (!session) return;
    remember(
      await request<Session>(`/sessions/${session.id}/resources/${id}`, {
        method: "DELETE",
      }),
    );
  };
  const composer = (
    <Composer
      settings={settings}
      onSettings={setSettings}
      prompt={prompt}
      onPrompt={setPrompt}
      onOptimize={() => setModal("optimize")}
      onHistory={() => void openHistory()}
      onSubmit={() => void submit()}
      busy={busy || restoring}
      conversation={page === "conversation"}
      allowFullRevision={allowFullRevision}
      onFullRevision={setAllowFullRevision}
    />
  );
  return (
    <div
      className={
        "app cw-agent " + (page === "conversation" ? "conversation-page" : "")
      }
    >
      {page === "home" ? (
        <AgentHomeHeader
          ready={ready}
          onNew={newSession}
          onHistory={() => void openHistory()}
          historyLabel="课件历史备课"
        />
      ) : (
        <ConversationHeader
          chapter={settings.chapter}
          period={settings.period}
          product="互动课件"
          onBack={() => {
            if (busy) {
              returnHomeRef.current = true;
              setPage("home");
            } else resetSession(true);
          }}
          onSources={() => setModal("resources")}
          onHistory={() => void openHistory()}
          onNew={newSession}
          busy={busy}
          historyLabel="课件历史备课"
          newLabel="新建课件"
        />
      )}

      {error && (
        <div role="alert" className="error-banner">
          <AlertCircle size={18} />
          <span>{error}</span>
          <button
            className="icon-button"
            aria-label="关闭课件错误"
            onClick={() => setError("")}
          >
            <X size={17} />
          </button>
        </div>
      )}
      {page === "home" ? (
        <main className="home-main">
          <AgentHero
            active="courseware"
            onChange={(kind) => {
              if (kind === "guide") onGuide();
              else if (kind === "practice") onPractice?.();
            }}
          />
          <section className="workspace">
            {session && (job || sending) && (
              <BackgroundTaskNotice
                product="互动课件"
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
              busy={busy || restoring}
              prefix="课件"
              uploadCount={session?.resources.length || 0}
            />
            {composer}
            <AppliedOptions
              optimized={
                JSON.stringify(settings.options) !==
                JSON.stringify(defaultSettings().options)
              }
              onOptimize={() => setModal("optimize")}
              hint="从本课教材出发，生成可编辑的互动课件"
            />
          </section>
          <AgentHomeFooter />
        </main>
      ) : (
        <main className="chat-main">
          {session && session.sources.length > 0 && (
            <button
              className="text-button agent-source-review"
              onClick={() => setModal("sources")}
            >
              <Library size={16} />
              本课引用来源（{session.sources.length}）
            </button>
          )}
          {session && (
            <ConversationView
              request={
                [...session.messages].reverse().find((m) => m.role === "user")
                  ?.content || "请根据本课内容生成互动课件。"
              }
              product="互动课件"
              job={job}
              busy={busy}
              onSources={() => setModal("resources")}
              onRetry={() => void submit(true)}
              version={version}
              versions={session.versions}
              onVersion={setVersionId}
              versionLabel="课件版本"
            >
              {version && (
                <Preview
                  key={version.id}
                  sid={session.id}
                  version={version}
                  onSources={() => setModal("sources")}
                />
              )}
            </ConversationView>
          )}
          {version && !busy && (
            <RevisionSuggestions
              chapter={settings.chapter}
              period={settings.period}
              version={version.number}
              items={["精简情境导入", "增加课堂互动", "补充易错提醒"]}
              disabled={version.id !== session?.versions.at(-1)?.id}
              onSuggestion={(text) => void submit(false, text)}
            />
          )}
          <ConversationComposer disclaimer="内容由 AI 辅助生成，请结合教材与学情复核。最终排版以 PPTX 为准。">
            {composer}
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
          onClose={close}
        />
      )}
      {(modal === "resources" || modal === "sources") && (
        <Resources
          key={modal}
          initialTab={modal === "sources" ? "sources" : "uploads"}
          resources={session?.resources || []}
          sources={version?.sources || session?.sources || []}
          onUpload={upload}
          onDelete={deleteResource}
          busy={busy}
          onClose={close}
        />
      )}
      {modal === "history" && (
        <Modal title="互动课件历史" onClose={close} className="history-modal">
          <div className="modal-scroll">
            {history.length ? (
              history.map((s) => (
                <button
                  className="history-item"
                  key={s.id}
                  disabled={busy}
                  onClick={() => void load(s.id)}
                >
                  <span className="history-icon">
                    <Presentation size={22} />
                  </span>
                  <div>
                    <strong>{s.settings.chapter}</strong>
                    <p>
                      {s.settings.period} · {s.version_count} 个版本 ·{" "}
                      {new Date(s.updated_at).toLocaleString("zh-CN")}
                    </p>
                  </div>
                </button>
              ))
            ) : (
              <p className="cw-empty">还没有互动课件记录，从第一份课件开始。</p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { ListChecks, Library, Sparkles, X } from "lucide-react";
import Modal from "../../components/Modal";
import { request, post } from "./api";
import {
  defaultSettings,
  type AgentId,
  type Job,
  type Options,
  type Session,
  type Settings,
  type Summary,
} from "./types";
import { applyOptimization } from "./prompt";
import OptimizeDialog from "./OptimizeDialog";
import Resources from "./Resources";
import Preview from "./Preview";
import "./practice.css";
import {
  AgentHomeHeader,
  AgentHero,
  LessonToolbar,
  AgentHomeFooter,
  AppliedOptions,
} from "../../components/AgentHome";
import SharedComposer from "../../components/Composer";
import {
  ConversationHeader,
  ConversationView,
  ConversationComposer,
  RevisionSuggestions,
  BackgroundTaskNotice,
} from "../../components/AgentConversation";
const SESSION_KEY = "qiming-practice-session",
  DRAFT_KEY = "qiming-practice-draft";
function initialDraft(): { settings: Settings; prompt: string } {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null");
    if (d?.settings?.options && typeof d.prompt === "string") return d;
  } catch {
    /* Start a fresh draft if browser storage is stale. */
  }
  return { settings: defaultSettings(), prompt: "" };
}
export default function PracticeApp({
  onAgentChange,
}: {
  onAgentChange: (id: AgentId) => void;
}) {
  const [initial] = useState(initialDraft),
    [settings, setSettings] = useState(initial.settings),
    [prompt, setPrompt] = useState(initial.prompt),
    [session, setSession] = useState<Session | null>(null),
    [job, setJob] = useState<Job>(),
    [versionId, setVersionId] = useState("");
  const [modal, setModal] = useState<
      "optimize" | "resources" | "sources" | "history" | null
    >(null),
    [history, setHistory] = useState<Summary[]>([]),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [sending, setSending] = useState(false),
    [ready, setReady] = useState(false),
    [restoring, setRestoring] = useState(true);
  const [homeRequested, setHomeRequested] = useState(false);
  const locked = useRef(false),
    creating = useRef<Promise<Session> | null>(null);
  const busy = sending || job?.status === "queued" || job?.status === "running";
  const version =
      session?.versions.find((v) => v.id === versionId) ||
      session?.versions.at(-1),
    conversation =
      !!session &&
      (!!session.jobs.length || !!session.versions.length) &&
      !homeRequested;
  useEffect(() => {
    let cancelled = false;
    request<{ ready: boolean }>("/health")
      .then((h) => {
        if (!cancelled) setReady(h.ready);
      })
      .catch(() => {});
    const id = localStorage.getItem(SESSION_KEY);
    if (!id) {
      setRestoring(false);
      return;
    }
    request<Session>("/sessions/" + id)
      .then((s) => {
        if (cancelled) return;
        setSession(s);
        setJob(s.jobs.at(-1));
        setSettings(initial.settings);
        if (!localStorage.getItem(DRAFT_KEY)) setSettings(s.settings);
      })
      .catch(() => {
        if (!cancelled) localStorage.removeItem(SESSION_KEY);
      })
      .finally(() => {
        if (!cancelled) setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  useEffect(() => {
    if (!restoring)
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ settings, prompt }));
  }, [settings, prompt, restoring]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 3500);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await request<Job>("/jobs/" + job!.id);
        if (cancelled) return;
        if (next.status === "completed" || next.status === "failed") {
          const s = await request<Session>("/sessions/" + next.session_id);
          if (cancelled) return;
          setSession(s);
          setJob(next);
          if (next.version_id) setVersionId(next.version_id);
          return;
        }
        setJob(next);
        timer = setTimeout(poll, 1100);
      } catch (e) {
        if (!cancelled) {
          setError((e as Error).message);
          timer = setTimeout(poll, 3000);
        }
      }
    }
    timer = setTimeout(poll, 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [job?.id, job?.status]);
  async function ensureSession() {
    if (session) return session;
    if (!creating.current)
      creating.current = post<Session>("/sessions", settings);
    try {
      const s = await creating.current;
      setSession(s);
      localStorage.setItem(SESSION_KEY, s.id);
      return s;
    } finally {
      creating.current = null;
    }
  }
  async function refresh(sid: string) {
    const s = await request<Session>("/sessions/" + sid);
    setSession(s);
    return s;
  }
  async function submit(options?: { retry?: boolean; prompt?: string }) {
    if (locked.current || busy || restoring) return;
    if (!settings.chapter.trim()) {
      setError("请填写章节或知识点");
      return;
    }
    const retry = !!options?.retry;
    const instruction = retry
      ? session?.messages.filter((m) => m.role === "user").at(-1)?.content ||
        prompt
      : options?.prompt ||
        prompt.trim() ||
        (version
          ? "请根据本课要求调整当前限时练习，保留未涉及内容。"
          : "请根据本课内容生成一份限时练习，并提供独立答案与解析。");
    if (instruction.length > 8000) {
      setError("提示词超过8000字，请精简要求");
      return;
    }
    if (!retry && version && version.id !== session?.versions.at(-1)?.id) {
      setError("请切换至最新版本后修改，历史版本保留供查看。");
      return;
    }
    setHomeRequested(false);
    locked.current = true;
    setSending(true);
    setError("");
    try {
      const s = await ensureSession();
      await request("/sessions/" + s.id, {
        method: "PATCH",
        body: JSON.stringify(settings),
      });
      const revision = retry ? job?.kind === "revision" : !!version;
      const baseId = retry ? job?.base_version_id : version?.id;
      const next = await post<Job>(
        `/sessions/${s.id}/${revision ? "revise" : "generate"}`,
        {
          prompt: instruction,
          ...(revision ? { base_version_id: baseId } : {}),
        },
      );
      setJob(next);
      setPrompt("");
      const fresh = await refresh(s.id);
      setJob(fresh.jobs.at(-1) || next);
      if (fresh.versions.at(-1)) setVersionId(fresh.versions.at(-1)!.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSending(false);
      locked.current = false;
    }
  }
  function apply(options: Options) {
    setSettings({ ...settings, options });
    setPrompt(applyOptimization(prompt, options));
    setModal(null);
    setNotice("优化要求已写入提示词，可编辑后提交");
  }
  async function openHistory() {
    setModal("history");
    try {
      setHistory(await request<Summary[]>("/sessions"));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function loadSession(id: string) {
    if (busy) {
      setNotice("请等待当前限时练习任务完成");
      return;
    }
    try {
      const s = await refresh(id);
      setSettings(s.settings);
      setJob(s.jobs.at(-1));
      setVersionId(s.versions.at(-1)?.id || "");
      setPrompt("");
      setError("");
      setModal(null);
      setHomeRequested(false);
      localStorage.setItem(SESSION_KEY, id);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function reset() {
    if (busy) {
      setNotice("请等待当前限时练习任务完成");
      return;
    }
    setHomeRequested(false);
    setSession(null);
    setJob(undefined);
    setVersionId("");
    setSettings(defaultSettings());
    setPrompt("");
    setError("");
    setModal(null);
    localStorage.removeItem(SESSION_KEY);
  }
  async function upload(file: File, category: string) {
    const s = await ensureSession();
    const form = new FormData();
    form.append("file", file);
    form.append("category", category);
    await request(`/sessions/${s.id}/resources`, {
      method: "POST",
      body: form,
    });
    await refresh(s.id);
  }
  async function remove(id: string) {
    if (!session) return;
    const s = await request<Session>(
      `/sessions/${session.id}/resources/${id}`,
      { method: "DELETE" },
    );
    setSession(s);
  }
  const composer = (
    <SharedComposer
      settings={settings}
      onSettings={setSettings}
      prompt={prompt}
      onPrompt={setPrompt}
      onSubmit={() => void submit()}
      onOptimize={() => setModal("optimize")}
      onHistory={() => void openHistory()}
      busy={busy || restoring}
      conversation={conversation}
      product="限时练习"
      chapterLabel="限时练习章节"
      periodLabel="限时练习课时"
      promptLabel={conversation ? "继续修改限时练习" : "限时练习要求"}
      historyLabel="历史限时练习"
      placeholder={
        conversation
          ? "描述需要调整的题目、难度或题量…"
          : "例如：15 分钟，5 道选择题和 2 道解答题，包含分层练习与答案解析…"
      }
    />
  );
  return (
    <div className={"app tp-app " + (conversation ? "conversation-page" : "")}>
      {!conversation ? (
        <AgentHomeHeader
          ready={ready}
          onNew={reset}
          onHistory={() => void openHistory()}
          historyLabel="限时练习历史"
        />
      ) : (
        <ConversationHeader
          chapter={settings.chapter}
          period={settings.period}
          product="限时练习"
          onBack={() => (busy ? setHomeRequested(true) : reset())}
          onSources={() => setModal("resources")}
          onHistory={() => void openHistory()}
          onNew={reset}
          busy={busy}
          historyLabel="限时练习历史"
          newLabel="新建练习"
        />
      )}

      {error && (
        <div role="alert" className="error-banner">
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

      <main className={conversation ? "chat-main" : "home-main"}>
        {!conversation && (
          <AgentHero active="practice" onChange={onAgentChange} />
        )}
        {conversation && session && (
          <>
            {session.sources.length > 0 && (
              <button
                className="text-button agent-source-review"
                onClick={() => setModal("sources")}
              >
                <Library size={16} />
                本课引用来源（{session.sources.length}）
              </button>
            )}
            <ConversationView
              request={
                [...session.messages].reverse().find((m) => m.role === "user")
                  ?.content || "请根据本课内容生成限时练习。"
              }
              product="限时练习"
              job={job}
              busy={busy}
              onSources={() => setModal("resources")}
              onRetry={() => void submit({ retry: true })}
              version={version}
              versions={session.versions}
              onVersion={setVersionId}
              versionLabel="限时练习版本"
              progressExtra={
                <>
                  {job?.effective_requirements && (
                    <p className="progress-requirements">
                      本次要求：{job.effective_requirements.duration} 分钟 ·{" "}
                      {job.effective_requirements.total_score} 分
                    </p>
                  )}
                  {!!job?.source_issues?.length && (
                    <details className="source-issues">
                      <summary>查看资料缺口</summary>
                      <ul>
                        {job.source_issues.map((text, i) => (
                          <li key={i}>{text}</li>
                        ))}
                      </ul>
                    </details>
                  )}
                </>
              }
            >
              {version && (
                <Preview
                  key={version.id}
                  version={version}
                  sessionId={session.id}
                  onSources={() => setModal("sources")}
                />
              )}
            </ConversationView>
            {version && !busy && (
              <RevisionSuggestions
                chapter={settings.chapter}
                period={settings.period}
                version={version.number}
                items={["增加分层练习", "调整题目难度", "补充答案解析"]}
                disabled={version.id !== session.versions.at(-1)?.id}
                onSuggestion={(text) => void submit({ prompt: text })}
              />
            )}
          </>
        )}
        {conversation ? (
          <ConversationComposer>{composer}</ConversationComposer>
        ) : (
          <section className="workspace">
            {session && (job || sending) && (
              <BackgroundTaskNotice
                product="限时练习"
                busy={busy}
                sending={sending}
                status={job?.status}
                onResume={() => setHomeRequested(false)}
              />
            )}
            <LessonToolbar
              settings={settings}
              onSettings={setSettings}
              onResources={() => setModal("resources")}
              busy={busy || restoring}
              prefix="限时练习"
              uploadCount={session?.resources.length || 0}
            />
            {composer}
            <AppliedOptions
              optimized={
                JSON.stringify(settings.options) !==
                JSON.stringify(defaultSettings().options)
              }
              onOptimize={() => setModal("optimize")}
              hint="从本课教材出发，生成试题与独立答案解析"
            />
          </section>
        )}
        {!conversation && <AgentHomeFooter />}
      </main>
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
          onClose={() => setModal(null)}
        />
      )}
      {(modal === "resources" || modal === "sources") && (
        <Resources
          resources={session?.resources || []}
          sources={
            modal === "sources"
              ? version?.sources || []
              : session?.sources || []
          }
          snapshot={modal === "sources"}
          busy={busy}
          onClose={() => setModal(null)}
          onUpload={upload}
          onDelete={remove}
        />
      )}
      {modal === "history" && (
        <Modal
          title="历史限时练习"
          onClose={() => setModal(null)}
          className="tp-history"
        >
          <div className="modal-scroll">
            {history.length ? (
              history.map((s) => (
                <button
                  key={s.id}
                  className="tp-history-item"
                  disabled={busy}
                  onClick={() => void loadSession(s.id)}
                >
                  <ListChecks size={23} />
                  <span>
                    <strong>{s.settings.chapter}</strong>
                    <small>
                      {s.settings.period} · {s.version_count} 个版本 ·{" "}
                      {new Date(s.updated_at).toLocaleString("zh-CN", {
                        timeZone: "Asia/Shanghai",
                      })}
                    </small>
                  </span>
                </button>
              ))
            ) : (
              <p className="tp-hint">
                还没有历史限时练习，从本课内容开始生成吧。
              </p>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

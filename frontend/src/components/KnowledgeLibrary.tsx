import { useEffect, useId, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  FileText,
  LoaderCircle,
  Presentation,
  RefreshCw,
} from "lucide-react";
import { api, post, type Source } from "../agents/study-guide/services/api";
import { useWorkbench } from "./AgentWorkbench";
import { subjectLessons } from "../subjects";
import { SourceCard } from "./Resources";
import { LIBRARY_UPDATED_EVENT } from "../knowledgeLibrary";
const subjects = Object.keys(subjectLessons);

type Document = {
  id: string;
  title: string;
  dataset_name: string;
  dataset_id?: string;
  subject?: string;
  kind: string;
  chunks: Source[];
};
type Library = {
  documents: Document[];
  chunk_count: number;
  synced_at: string | null;
};
function validLibrary(value: Library) {
  if (!Array.isArray(value.documents)) throw new Error("知识库目录返回结构无效，请重新同步");
  return value;
}
export default function KnowledgeLibrary({
  libraryPath = "",
}: {
  libraryPath?: string;
}) {
  const target = useWorkbench()?.libraryTarget;
  const libraryRef = useRef<HTMLElement>(null);
  const tabId = useId();
  const [selectedSubject, setSelectedSubject] = useState(target?.subject || "化学");
  const [data, setData] = useState<Library>(),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [query, setQuery] = useState("");
  useEffect(() => {
    if (!target) return;
    setSelectedSubject(target.subject);
    setQuery("");
    if (!target.chapter) libraryRef.current?.scrollIntoView?.({block:"start",behavior:"smooth"});
  }, [target]);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let value = validLibrary(await api<Library>(libraryPath + "/library"));
        if (!value.synced_at || value.documents.some(d => d.dataset_id && d.subject === undefined)) {
          value = validLibrary(await post<Library>(libraryPath + "/library/sync", {}));
          if (!libraryPath) window.dispatchEvent(new Event(LIBRARY_UPDATED_EVENT));
        }
        if (!cancelled) setData(value);
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [libraryPath]);
  const sync = async () => {
    setLoading(true);
    setError("");
    try {
      setData(validLibrary(await post<Library>(libraryPath + "/library/sync", {})));
      if (!libraryPath) window.dispatchEvent(new Event(LIBRARY_UPDATED_EVENT));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const documents =
    data?.documents.filter((d) =>
      (!d.subject || d.subject === selectedSubject) && `${d.subject || ""} ${d.title} ${d.dataset_name}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) || [];
  const normalizeTitle = (value: string) => value.replace(/\.(pdf|docx?|pptx?|txt|md)$/i, "").replace(/[\s·—_：:]/g, "");
  const targetTitle = target?.chapter ? normalizeTitle(target.chapter) : "";
  const matchedId = targetTitle && target?.subject === selectedSubject
    ? documents.find(file => normalizeTitle(file.title).includes(targetTitle))?.id : undefined;
  return (
    <section ref={libraryRef} className="knowledge-library" aria-label="知识库全量资料">
      <div className="source-list-header">
        <h3>
          <BookOpen size={18} /> 知识库全部资料
        </h3>
        <button
          className="button secondary small"
          disabled={loading}
          onClick={() => void sync()}
        >
          {loading ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}{" "}
          {loading ? "正在同步全量资料…" : "同步知识库"}
        </button>
      </div>
      <div className="library-subject-tabs" role="tablist" aria-label="知识库学科">
        {subjects.map((subject, index) => <button key={subject} id={`${tabId}-tab-${index}`} role="tab"
          aria-selected={selectedSubject === subject} aria-controls={`${tabId}-panel`}
          tabIndex={selectedSubject === subject ? 0 : -1}
          onClick={() => setSelectedSubject(subject)}
          onKeyDown={event => {
            const next = event.key === "Home" ? 0 : event.key === "End" ? subjects.length - 1 : event.key === "ArrowRight" ? (index+1)%subjects.length : event.key === "ArrowLeft" ? (index+subjects.length-1)%subjects.length : -1;
            if (next < 0) return;
            event.preventDefault();
            setSelectedSubject(subjects[next]);
            event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
          }}>{subject}</button>)}
      </div>
      {data && (
        <p className="field-hint">
          {data.documents.length} 份资料 · {data.chunk_count} 个片段 · 上次同步{" "}
          {data.synced_at
            ? new Date(data.synced_at).toLocaleString()
            : "尚未同步"}
        </p>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <input
        className="library-search"
        aria-label="筛选知识库资料"
        placeholder="按文件名或知识库筛选资料"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div role="tabpanel" id={`${tabId}-panel`} aria-labelledby={`${tabId}-tab-${subjects.indexOf(selectedSubject)}`}>
        {Array.from(new Set(documents.map(d => d.dataset_id || d.dataset_name))).map(dataset => {
          const files=documents.filter(d => (d.dataset_id || d.dataset_name) === dataset);
          return <details className="library-dataset-folder" key={`${dataset}-${target?.subject === selectedSubject ? target.requestId : ""}`} open>
            <summary><BookOpen size={16} />{files[0].dataset_name}<small>{files[0].subject ? "" : "未分类 · "}{files.length} 份文件</small></summary>
            {files.map(d => <DocumentCard key={d.id} document={d} libraryPath={libraryPath} focusRequest={d.id === matchedId ? target?.requestId : undefined} />)}
          </details>;
        })}
      {!loading && !documents.length && (
        <p className="field-hint">
          {query ? "没有匹配的资料。" : `${selectedSubject}暂无知识库资料。`}
        </p>
      )}
      </div>
    </section>
  );
}
function DocumentCard({
  document: d,
  libraryPath,
  focusRequest,
}: {
  focusRequest?: number;
  document: Document;
  libraryPath: string;
}) {
  const fileRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (focusRequest === undefined) return;
    setOpen(true);
    fileRef.current?.scrollIntoView?.({block:"nearest",behavior:"smooth"});
  }, [focusRequest]);
  const [open, setOpen] = useState(false),
    [limit, setLimit] = useState(20);
  return (
    <div ref={fileRef} className={"source-card library-document" + (focusRequest !== undefined ? " library-document-focused" : "")}>
      <button
        className="source-title"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {d.kind === "presentation" ? (
          <Presentation size={20} />
        ) : (
          <FileText size={20} />
        )}
        <div>
          <strong>{d.title}</strong>
          <small>
            {d.dataset_name} · {d.chunks.length} 个片段
            {d.kind === "presentation" ? " · PPT" : ""}
          </small>
        </div>
        <ChevronDown size={16} className={open ? "flipped" : ""} />
      </button>
      {open && (
        <div className="source-details">
          <a
            className="button secondary small"
            href={`/api${libraryPath}/library/${encodeURIComponent(d.id)}/original`}
            target="_blank"
            rel="noreferrer"
          >
            下载原文件
          </a>
          {!d.chunks.length && (
            <p className="field-hint">
              知识库尚无已解析片段，可下载原文件查看。
            </p>
          )}
          {d.chunks.slice(0, limit).map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              library
              snapshot
              busy={false}
            />
          ))}
          {limit < d.chunks.length && (
            <button
              className="button secondary small"
              onClick={() => setLimit(limit + 20)}
            >
              继续显示片段（剩余 {d.chunks.length - limit} 个）
            </button>
          )}
        </div>
      )}
    </div>
  );
}

import { useEffect, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  FileText,
  LoaderCircle,
  Presentation,
  RefreshCw,
} from "lucide-react";
import { api, post, type Source } from "../agents/study-guide/services/api";
import { SourceCard } from "./Resources";
type Document = {
  id: string;
  title: string;
  dataset_name: string;
  kind: string;
  chunks: Source[];
};
type Library = {
  documents: Document[];
  chunk_count: number;
  synced_at: string | null;
};
export default function KnowledgeLibrary({
  libraryPath = "",
}: {
  libraryPath?: string;
}) {
  const [data, setData] = useState<Library>(),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [query, setQuery] = useState("");
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        let value = await api<Library>(libraryPath + "/library");
        if (!value.synced_at)
          value = await post<Library>(libraryPath + "/library/sync", {});
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
      setData(await post<Library>(libraryPath + "/library/sync", {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const documents =
    data?.documents.filter((d) =>
      `${d.title} ${d.dataset_name}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) || [];
  return (
    <section className="knowledge-library" aria-label="知识库全量资料">
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
      {documents.map((d) => (
        <DocumentCard key={d.id} document={d} libraryPath={libraryPath} />
      ))}
      {!loading && !documents.length && (
        <p className="field-hint">
          {query ? "没有匹配的资料。" : "暂无知识库资料，请同步知识库。"}
        </p>
      )}
    </section>
  );
}
function DocumentCard({
  document: d,
  libraryPath,
}: {
  document: Document;
  libraryPath: string;
}) {
  const [open, setOpen] = useState(false),
    [limit, setLimit] = useState(20);
  return (
    <div className="source-card library-document">
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

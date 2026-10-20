import { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  ChevronDown,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import Modal from "../../components/Modal";
import { PREFIX, post, request } from "./api";
import type { Source } from "./types";
const CATEGORIES: Record<string, string> = {
  textbook: "教材",
  teacher_book: "教师用书",
  exercises: "课时题库",
  practice: "必刷题",
  exam: "高考真题",
};
type LibraryDocument = {
  id: string;
  title: string;
  dataset_name: string;
  chunks: Source[];
};
type Catalog = {
  documents: LibraryDocument[];
  chunk_count: number;
  synced_at: string | null;
};
function SourceItem({
  source,
  onDelete,
}: {
  source: Source;
  onDelete?: (id: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="tp-source">
      <summary>
        <BookOpen size={17} />
        <div>
          <strong>{source.title}</strong>
          <small>
            {CATEGORIES[source.category] || "参考资料"} · {source.locator}
          </small>
        </div>
        <ChevronDown size={16} />
      </summary>
      <div className="tp-source-body">
        <pre>{source.evidence}</pre>
        {onDelete && (
          <button
            className="text-button"
            disabled={busy}
            onClick={() => void run(() => onDelete(source.id))}
          >
            <Trash2 size={15} />
            删除本课资料
          </button>
        )}
        {error && (
          <p role="alert" className="inline-error">
            {error}
          </p>
        )}
      </div>
    </details>
  );
}
function Library() {
  const [catalog, setCatalog] = useState<Catalog>(),
    [busy, setBusy] = useState(true),
    [error, setError] = useState(""),
    [query, setQuery] = useState("");
  useEffect(() => {
    let cancelled = false;
    request<Catalog>("/library")
      .then(async (c) => (c.synced_at ? c : post<Catalog>("/library/sync", {})))
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setBusy(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);
  async function sync() {
    setBusy(true);
    setError("");
    try {
      setCatalog(await post<Catalog>("/library/sync", {}));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="tp-library">
      <div className="tp-row">
        <h3>知识库全部资料</h3>
        <button
          className="button secondary small"
          disabled={busy}
          onClick={() => void sync()}
        >
          {busy ? (
            <LoaderCircle size={15} className="spin" />
          ) : (
            <RefreshCw size={15} />
          )}
          同步知识库
        </button>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          {error}
        </p>
      )}
      <input
        aria-label="筛选知识库资料"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="按文件名或知识库名筛选"
      />
      {catalog && (
        <p className="tp-hint">
          {catalog.documents.length} 份资料 · {catalog.chunk_count} 个片段
        </p>
      )}
      {catalog?.documents
        .filter((d) =>
          (d.title + d.dataset_name)
            .toLowerCase()
            .includes(query.toLowerCase()),
        )
        .map((d) => (
          <LibraryCard key={d.id} document={d} />
        ))}
    </section>
  );
}
function LibraryCard({ document: d }: { document: LibraryDocument }) {
  const [limit, setLimit] = useState(20);
  return (
    <details className="tp-source">
      <summary>
        <BookOpen size={18} />
        <div>
          <strong>{d.title}</strong>
          <small>
            {d.dataset_name} · {d.chunks.length} 个片段
          </small>
        </div>
        <ChevronDown size={16} />
      </summary>
      <div className="tp-source-body">
        <a
          className="button secondary small"
          target="_blank"
          rel="noreferrer"
          href={`${PREFIX}/library/${encodeURIComponent(d.id)}/original`}
        >
          查看原文件
        </a>
        {d.chunks.slice(0, limit).map((s) => (
          <SourceItem key={s.id} source={s} />
        ))}
        {d.chunks.length > limit && (
          <button className="text-button" onClick={() => setLimit(limit + 20)}>
            继续显示片段
          </button>
        )}
      </div>
    </details>
  );
}
export default function Resources({
  resources,
  sources,
  snapshot,
  busy,
  onClose,
  onUpload,
  onDelete,
}: {
  resources: Source[];
  sources: Source[];
  snapshot: boolean;
  busy: boolean;
  onClose: () => void;
  onUpload: (f: File, c: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
}) {
  const [category, setCategory] = useState("textbook"),
    [working, setWorking] = useState(false),
    [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  async function upload(file?: File) {
    if (!file || busy || working) return;
    setWorking(true);
    setError("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("文件超过20MB");
      await onUpload(file, category);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
      if (input.current) input.current.value = "";
    }
  }
  return (
    <Modal
      title={snapshot ? "本版本引用来源" : "资料库 · 限时练习"}
      onClose={onClose}
      className="tp-resources"
    >
      <div className="modal-scroll">
        {!snapshot && (
          <>
            <div
              className="tp-dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                void upload(e.dataTransfer.files[0]);
              }}
            >
              <Upload size={25} />
              <strong>上传本课参考资料</strong>
              <p>TXT、Markdown、DOCX、文字 PDF，每份不超过 20MB</p>
              <div className="tp-row">
                <select
                  aria-label="上传资料类型"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  {Object.entries(CATEGORIES).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                <button
                  className="button primary small"
                  disabled={working || busy}
                  onClick={() => input.current?.click()}
                >
                  {working ? "正在上传…" : "选择文件"}
                </button>
              </div>
              <input
                ref={input}
                hidden
                type="file"
                accept=".txt,.md,.docx,.pdf"
                onChange={(e) => void upload(e.target.files?.[0])}
              />
            </div>
            {error && (
              <p className="inline-error" role="alert">
                {error}
              </p>
            )}
            <Library />
            <h3>本课上传资料</h3>
            {!resources.length && <p className="tp-hint">尚未上传本课资料。</p>}
            {resources.map((s) => (
              <SourceItem
                key={s.id}
                source={s}
                onDelete={busy ? undefined : onDelete}
              />
            ))}
          </>
        )}
        {sources.length > 0 && (
          <>
            <h3>{snapshot ? "生成时的不可变来源快照" : "本课检索命中"}</h3>
            {sources
              .filter((s) => snapshot || !resources.some((r) => r.id === s.id))
              .map((s) => (
                <SourceItem key={s.id} source={s} />
              ))}
          </>
        )}
      </div>
      <footer className="modal-footer">
        <p className="tp-hint">
          {snapshot
            ? "历史版本保留生成时的题源。"
            : "本课资料仅属于限时练习，不与其他 Agent 会话共享。"}
        </p>
        <button className="button dark" onClick={onClose}>
          完成
        </button>
      </footer>
    </Modal>
  );
}

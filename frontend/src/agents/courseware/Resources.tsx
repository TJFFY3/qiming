import { useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  FileText,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import Modal from "../../components/Modal";
import { PREFIX, post, request } from "./api";
import type { LibraryData, Source } from "./types";
export default function Resources({
  resources,
  sources,
  onUpload,
  onDelete,
  onClose,
  busy,
  initialTab = "uploads",
}: {
  resources: Source[];
  sources: Source[];
  onUpload: (file: File, category: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onClose: () => void;
  busy: boolean;
  initialTab?: "uploads" | "library" | "sources";
}) {
  const [tab, setTab] = useState<"uploads" | "library" | "sources">(initialTab),
    [category, setCategory] = useState("textbook"),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false),
    [library, setLibrary] = useState<LibraryData>(),
    [query, setQuery] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (tab !== "library" || library) return;
    let active = true;
    setLoading(true);
    request<LibraryData>("/library")
      .then((value) => {
        if (active) setLibrary(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tab, library]);
  const action = async (fn: () => Promise<void>) => {
    setLoading(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };
  const upload = (file?: File) => {
    if (file) void action(() => onUpload(file, category));
  };
  return (
    <Modal title="课件资料库" onClose={onClose} className="cw-resources">
      <div className="modal-scroll">
        <div className="cw-resource-tabs">
          {(
            [
              ["uploads", "本课上传资料"],
              ["library", "知识库"],
              ["sources", "本课引用来源"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              aria-pressed={tab === id}
              onClick={() => setTab(id)}
            >
              {label}
            </button>
          ))}
        </div>
        {error && (
          <p role="alert" className="cw-inline-error">
            {error}
          </p>
        )}
        {tab === "uploads" && (
          <>
            <div
              className="cw-upload"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!busy && !loading) upload(e.dataTransfer.files[0]);
              }}
            >
              <Upload size={28} />
              <strong>上传本课参考资料</strong>
              <p>支持 TXT、Markdown、DOCX、文字 PDF · 每份 20MB，最多 10 份</p>
              <div className="cw-actions">
                <select
                  aria-label="课件资料类别"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="textbook">教材</option>
                  <option value="teacher_book">教师用书</option>
                  <option value="exercises">课时题库</option>
                  <option value="practice">必刷题</option>
                  <option value="exam">高考真题</option>
                </select>
                <button
                  className="button primary"
                  disabled={busy || loading}
                  onClick={() => input.current?.click()}
                >
                  选择文件
                </button>
              </div>
              <input
                ref={input}
                hidden
                type="file"
                accept=".txt,.md,.docx,.pdf"
                onChange={(e) => {
                  upload(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </div>
            {resources.map((s) => (
              <article className="cw-source-card" key={s.id}>
                <div>
                  <FileText size={18} />
                  <strong>{s.title}</strong>
                  <button
                    className="icon-button"
                    aria-label={"删除" + s.title}
                    disabled={busy || loading}
                    onClick={() => void action(() => onDelete(s.id))}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
                <p>{s.evidence.slice(0, 500)}</p>
              </article>
            ))}
          </>
        )}
        {tab === "sources" &&
          (sources.length ? (
            sources.map((s) => (
              <article className="cw-source-card" key={s.id}>
                <strong>{s.title}</strong>
                <small>{s.locator}</small>
                <p>{s.evidence}</p>
              </article>
            ))
          ) : (
            <p className="cw-empty">生成课件后可查看本次实际引用的资料。</p>
          ))}
        {tab === "library" && (
          <>
            <div className="cw-library-toolbar">
              <input
                aria-label="筛选课件知识库"
                placeholder="搜索文件或知识库名称"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
              <button
                className="button secondary"
                disabled={loading}
                onClick={() =>
                  void action(async () =>
                    setLibrary(await post<LibraryData>("/library/sync", {})),
                  )
                }
              >
                <RefreshCw size={16} />
                同步知识库
              </button>
            </div>
            {!loading && !library?.documents.length && (
              <p className="cw-empty">尚未同步知识库，请点击“同步知识库”。</p>
            )}
            {library?.documents
              .filter((d) => (d.title + d.dataset_name).includes(query))
              .map((d) => (
                <details key={d.id} className="cw-source-card">
                  <summary>
                    <FileText size={17} />
                    <strong>{d.title}</strong>
                    <small>{d.chunks.length} 个片段</small>
                    <ChevronDown size={16} />
                  </summary>
                  <div className="cw-library-document">
                    <a
                      href={`${PREFIX}/library/${encodeURIComponent(d.id)}/original`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看原文件
                    </a>
                    {d.chunks.map((s) => (
                      <details className="cw-chunk" key={s.id}>
                        <summary>{s.locator || s.title || "资料片段"}</summary>
                        <p>{s.evidence}</p>
                      </details>
                    ))}
                  </div>
                </details>
              ))}
          </>
        )}
        {loading && (
          <div role="status" className="cw-loading">
            <LoaderCircle className="spin" size={20} />
            正在处理资料…
          </div>
        )}
      </div>
    </Modal>
  );
}

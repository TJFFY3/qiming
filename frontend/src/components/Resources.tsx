import { useState, useRef, useCallback } from "react";
import {
  Upload,
  BookOpen,
  FileText,
  LoaderCircle,
  ChevronDown,
  Trash2,
} from "lucide-react";
import type { Source } from "../agents/study-guide/services/api";
import Modal from "./Modal";
import KnowledgeLibrary from "./KnowledgeLibrary";
import { sourceNotes, sourceTitle } from "../sourceDisplay";
import SourceEvidence from "./SourceEvidence";
const categories: Record<string, string> = {
  textbook: "教材",
  teacher_book: "教师用书",
  exercises: "课时题库",
  practice: "必刷题",
  exam: "高考真题",
};
export type ResourcesProps = {
  sources: Source[];
  resources: Source[];
  onUpload: (f: File, category: string) => Promise<void>;
  onDelete?: (id: string) => Promise<void>;
  onClose: () => void;
  busy: boolean;
  snapshot?: boolean;
  recall?: boolean;
  sourceIssues?: string[];
  libraryPath?: string;
  productName?: string;
};
export default function Resources({
  sources,
  resources,
  onUpload,
  onDelete,
  onClose,
  busy,
  snapshot = false,
  recall = false,
  sourceIssues = [],
  libraryPath = "",
  productName = "导学案",
}: ResourcesProps) {
  const notes = sourceNotes(sourceIssues);
  const [category, setCategory] = useState("textbook");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const close = useCallback(onClose, [onClose]);
  const all = Array.from(
    new Map(
      (snapshot ? sources : [...resources, ...(recall ? sources : [])]).map(
        (s) => [s.id, s],
      ),
    ).values(),
  );
  const upload = async (file: File) => {
    if (busy || uploading) return;
    setUploading(true);
    setError("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("文件超过20MB");
      await onUpload(file, category);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setUploading(false);
      if (input.current) input.current.value = "";
    }
  };
  return (
    <Modal
      title={
        snapshot
          ? "当前版本 · 来源快照"
          : recall
            ? "本课检索命中片段"
            : "资料库"
      }
      onClose={close}
      className="resource-modal"
    >
      <div className="modal-scroll">
        <p className="panel-description">
          {snapshot || recall
            ? `此处仅保留本次${productName}生成使用的命中片段。`
            : `浏览 FastGPT 知识库全部资料与片段，包括 PPT；${productName}生成时按需求检索。`}
        </p>
        {!snapshot && !recall && (
          <div
            className="upload-zone"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy && !uploading && e.dataTransfer.files[0])
                void upload(e.dataTransfer.files[0]);
            }}
          >
            <div className="upload-icon">
              <Upload size={25} />
            </div>
            <h3>添加本课参考资料</h3>
            <p>支持 TXT、Markdown、DOCX、文字 PDF，单份不超过 20MB</p>
            <div>
              <select
                aria-label="上传资料类型"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                {Object.entries(categories).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
              <button
                className="button primary"
                disabled={uploading || busy}
                onClick={() => input.current?.click()}
              >
                {uploading ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <Upload size={16} />
                )}
                选择文件
              </button>
            </div>
            <input
              ref={input}
              hidden
              type="file"
              accept=".txt,.md,.docx,.pdf"
              onChange={(e) => {
                if (e.target.files?.[0]) void upload(e.target.files[0]);
              }}
            />
          </div>
        )}
        {!snapshot && !recall && <KnowledgeLibrary libraryPath={libraryPath} />}
        {notes.length > 0 && (
          <div className="source-issues">
            <strong>本版本资料说明</strong>
            <ul>
              {notes.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          </div>
        )}
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="source-list-header">
          <h3>{snapshot || recall ? "本次命中片段" : "本课上传资料"}</h3>
          <span>{all.length} 份来源</span>
        </div>
        {all.length ? (
          all.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              busy={busy}
              snapshot={snapshot}
              onDelete={
                !snapshot && resources.some((r) => r.id === source.id)
                  ? onDelete
                  : undefined
              }
            />
          ))
        ) : (
          <div className="empty-state">
            <BookOpen size={32} />
            <h3>{snapshot ? "暂无命中片段" : "尚未上传本课资料"}</h3>
            <p>可以上传教材或教师用书作为本课补充资料。</p>
          </div>
        )}
      </div>
      <footer className="modal-footer">
        <span className="field-hint">
          {snapshot
            ? "来源快照保留生成时的资料，不随后续上传或删除改变。"
            : "本课上传资料用于后续生成，历史版本保留原引用。"}
        </span>
        <button className="button dark" onClick={onClose}>
          完成
        </button>
      </footer>
    </Modal>
  );
}
export function SourceCard({
  source,
  busy,
  snapshot,
  library = false,
  onDelete,
}: {
  library?: boolean;
  onDelete?: (id: string) => Promise<void>;
  source: Source;
  busy: boolean;
  snapshot: boolean;
}) {
  const [open, setOpen] = useState(false),
    [working, setWorking] = useState(false),
    [deleteError, setDeleteError] = useState("");
  return (
    <div className="source-card">
      <button
        className="source-title"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <FileText size={20} />
        <div>
          <strong>
            {sourceTitle(library ? source.locator : source.title)}
          </strong>
          <small>
            {categories[source.category] || "参考资料"} · {source.locator}
          </small>
        </div>
        <ChevronDown size={16} className={open ? "flipped" : ""} />
      </button>
      {onDelete && !snapshot && (
        <div className="source-actions">
          <button
            className="button secondary small delete-resource"
            aria-label={`删除资料 ${sourceTitle(source.title)}`}
            disabled={busy || working}
            onClick={async () => {
              setWorking(true);
              setDeleteError("");
              try {
                await onDelete(source.id);
              } catch (e) {
                setDeleteError((e as Error).message);
              } finally {
                setWorking(false);
              }
            }}
          >
            {working ? (
              <LoaderCircle size={15} className="spin" />
            ) : (
              <Trash2 size={15} />
            )}{" "}
            删除
          </button>
          {deleteError && (
            <p className="inline-error" role="alert">
              {deleteError}
            </p>
          )}
        </div>
      )}
      {open && (
        <div className="source-details">
          <SourceEvidence text={source.evidence} />
        </div>
      )}
    </div>
  );
}

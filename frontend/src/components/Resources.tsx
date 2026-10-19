import { useState, useRef, useCallback } from "react";
import {
  Upload,
  BookOpen,
  FileText,
  CheckCircle2,
  LoaderCircle,
  ChevronDown,
} from "lucide-react";
import type { Source } from "../api";
import Modal from "./Modal";
import SourceEvidence from "./SourceEvidence";
const categories: Record<string, string> = {
  textbook: "教材",
  teacher_book: "教师用书",
  exercises: "课时题库",
  practice: "必刷题",
  exam: "高考真题",
};
export default function Resources({
  sources,
  resources,
  onUpload,
  onReview,
  onClose,
  busy,
  snapshot = false,
  sourceIssues = [],
}: {
  sources: Source[];
  resources: Source[];
  onUpload: (f: File, category: string) => Promise<void>;
  onReview: (s: Source, note: string, verified: boolean) => Promise<void>;
  onClose: () => void;
  busy: boolean;
  snapshot?: boolean;
  sourceIssues?: string[];
}) {
  const [category, setCategory] = useState("textbook");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const close = useCallback(onClose, [onClose]);
  const all = Array.from(
    new Map([...resources, ...sources].map((s) => [s.id, s])).values(),
  );
  const upload = async (file: File) => {
    setUploading(true);
    setError("");
    try {
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
      title={snapshot ? "当前版本 · 来源快照" : "资料库"}
      onClose={close}
      className="resource-modal"
    >
      <div className="modal-scroll">
        <p className="panel-description">
          基于 FastGPT 知识库与上传资料备课。检索命中会保留原始摘录，供你核对。
        </p>
        {!snapshot && (
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
        {sourceIssues.length > 0 && (
          <div className="source-issues">
            <strong>本版本资料缺口与待核验项</strong>
            <ul>
              {sourceIssues.map((issue, i) => (
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
          <h3>本课资料</h3>
          <span>
            {all.length} 份来源 · {all.filter((x) => x.verified).length}{" "}
            份已核对
          </span>
        </div>
        {all.length ? (
          all.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              onReview={onReview}
              busy={busy}
              snapshot={snapshot}
            />
          ))
        ) : (
          <div className="empty-state">
            <BookOpen size={32} />
            <h3>等待检索本课资料</h3>
            <p>提交备课要求后检索 FastGPT，也可以先上传教材或教师用书。</p>
          </div>
        )}
      </div>
      <footer className="modal-footer">
        <span className="field-hint">
          {snapshot
            ? "此处展示生成时的来源状态，不随资料库核对改变。"
            : "来源核对不会改变已保存版本；重新生成后生效。"}
        </span>
        <button className="button dark" onClick={onClose}>
          完成
        </button>
      </footer>
    </Modal>
  );
}
function SourceCard({
  source,
  onReview,
  busy,
  snapshot,
}: {
  source: Source;
  onReview: (s: Source, n: string, v: boolean) => Promise<void>;
  busy: boolean;
  snapshot: boolean;
}) {
  const [open, setOpen] = useState(false),
    [note, setNote] = useState(source.review_note || ""),
    [working, setWorking] = useState(false),
    [error, setError] = useState("");
  return (
    <div className="source-card">
      <button
        className="source-title"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <FileText size={20} />
        <div>
          <strong>{source.title}</strong>
          <small>
            {categories[source.category] || "参考资料"} · {source.locator}
          </small>
        </div>
        <span className={source.verified ? "verified-tag" : "draft-tag"}>
          {source.verified ? "已核对" : "待核对"}
        </span>
        <ChevronDown size={16} className={open ? "flipped" : ""} />
      </button>
      {open && (
        <div className="source-details">
          <SourceEvidence text={source.evidence} />
          {snapshot ? (
            <p className="field-hint">
              核对记录：{source.review_note || "本版本尚无核对记录"}
            </p>
          ) : (
            <>
              <label>
                核对记录
                <textarea
                  maxLength={1000}
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  placeholder="查看原文件后，记录核对的教材版本、位置与结论"
                />
              </label>
              {error && <p className="inline-error">{error}</p>}
              <button
                className="button secondary small"
                disabled={busy || working || !note.trim()}
                onClick={async () => {
                  setWorking(true);
                  try {
                    await onReview(source, note, !source.verified);
                    setError("");
                  } catch (e) {
                    setError((e as Error).message);
                  } finally {
                    setWorking(false);
                  }
                }}
              >
                {working ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <CheckCircle2 size={15} />
                )}{" "}
                {source.verified ? "撤销核对" : "我已核对原文"}
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

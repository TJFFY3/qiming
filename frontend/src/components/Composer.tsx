import { LessonToolbar } from "./AgentHome";
import { api } from "../agents/study-guide/services/api";
import { useWorkbench } from "./AgentWorkbench";
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowUp,
  Paperclip,
  BookOpen,
  History,
  SlidersHorizontal,
  Sparkles,
  LoaderCircle,
} from "lucide-react";
import type { Settings } from "../agents/study-guide/services/api";
export default function Composer<
  T extends { chapter: string; period: string; subject?: string; edition?: string; grade?: string; options?: object } = Settings,
>({
  settings,
  onSettings,
  prompt,
  onPrompt,
  onSubmit,
  onOptimize,
  onHistory,
  busy,
  conversation = false,
  product = "导学案",
  chapterLabel = "章节 / 知识点",
  periodLabel = "课时",
  promptLabel,
  historyLabel = "历史备课",
  placeholder,
  children,
}: {
  settings: T;
  onSettings: (s: T) => void;
  prompt: string;
  onPrompt: (v: string) => void;
  onSubmit: () => void;
  onOptimize: () => void;
  onHistory: () => void;
  busy: boolean;
  conversation?: boolean;
  product?: string;
  chapterLabel?: string;
  periodLabel?: string;
  promptLabel?: string;
  historyLabel?: string;
  placeholder?: string;
  children?: ReactNode;
}) {
  const [chapters, setChapters] = useState<string[]>([]);
  const [chapterSubject, setChapterSubject] = useState("");
  const [chapterError, setChapterError] = useState("");
  const currentLesson = useRef({settings, onSettings});
  currentLesson.current = {settings, onSettings};
  useEffect(() => {
    if (conversation) return;
    let active = true;
    setChapters([]);
    setChapterError("");
    api<{chapters: string[]}>("/library/chapters?subject=" + encodeURIComponent(settings.subject || "化学")).then(data => {
      if (!active) return;
      if (!Array.isArray(data.chapters) || !data.chapters.every(value => typeof value === "string" && value.trim())) throw new Error("知识库章节目录无效");
      setChapters(data.chapters);
      setChapterSubject(settings.subject || "化学");
      if (!data.chapters.length) { setChapterError("该学科知识库暂无章节，请同步资料或检查目录。"); return; }
    }).catch(error => { if (active) setChapterError((error as Error).message + "，暂保留当前课题。"); });
    return () => { active = false; };
  }, [settings.subject, conversation]);
  useEffect(() => {
    if (conversation || chapterSubject !== (settings.subject || "化学") || !chapters.length) return;
    const current = currentLesson.current;
    if (!chapters.includes(current.settings.chapter)) current.onSettings({...current.settings,chapter:chapters[0]});
  }, [chapters, chapterSubject, settings.subject, settings.chapter, conversation]);
  const periods = ["第一课时", "第二课时"];
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const attachmentInput = useRef<HTMLInputElement>(null);
  const canSubmit =
    !busy && !uploading && !!settings.chapter.trim() && (!conversation || !!prompt.trim());
  const workbench = useWorkbench();
  const uploadAttachment = async (file: File) => {
    if (!workbench?.onUpload || busy || uploading) return;
    setUploading(true);
    setUploadError("");
    try {
      if (file.size > 20 * 1024 * 1024) throw new Error("文件超过20MB");
      await workbench.onUpload(file, "textbook");
    } catch (error) {
      setUploadError((error as Error).message);
    } finally {
      setUploading(false);
      if (attachmentInput.current) attachmentInput.current.value = "";
    }
  };
  return (
    <div className={"composer " + (conversation ? "compact" : "")}>
      {!conversation && (
        <div className="sentence">
          <span>基于</span>
          <LessonToolbar inline settings={settings} onSettings={onSettings} onResources={() => {}} busy={busy || uploading} prefix={product === "导学案" ? "" : product === "互动课件" ? "课件" : product} />
          <label className="chapter-chip">
            <BookOpen size={23} />
            <select
              aria-label={chapterLabel}
              disabled={busy}
              value={settings.chapter}
              onChange={(e) =>
                onSettings({ ...settings, chapter: e.target.value })
              }
            >
              {!chapters.includes(settings.chapter) && (
                <option value={settings.chapter}>{settings.chapter}</option>
              )}
              {chapters.map((chapter) => (
                <option key={chapter} value={chapter}>
                  {chapter}
                </option>
              ))}
            </select>
          </label>
          <span>生成</span>
          <label className="period-chip">
            <select
              aria-label={periodLabel}
              disabled={busy}
              value={settings.period}
              onChange={(e) =>
                onSettings({ ...settings, period: e.target.value })
              }
            >
              {periods.map((period) => (
                <option key={period} value={period}>
                  {period}
                </option>
              ))}
            </select>
          </label>
          <span>{product}</span>
        </div>
      )}
      <textarea
        className={
          /【[^【\n]*优化(?:提示|设置)】/.test(prompt)
            ? "optimization-prompt"
            : undefined
        }
        aria-label={
          promptLabel || (conversation ? "继续修改导学案" : "备课要求")
        }
        disabled={busy}
        value={prompt}
        maxLength={8000}
        onChange={(e) => onPrompt(e.target.value)}
        placeholder={
          placeholder ||
          (conversation
            ? "继续对话，随时调整这节课的设计，例如：增加互动环节…"
            : "例如：以生活情境导入，安排小组探究，突出重点和易错点…")
        }
        onKeyDown={(e) => {
          if (
            (e.ctrlKey || e.metaKey) &&
            e.key === "Enter" &&
            canSubmit &&
            !e.nativeEvent.isComposing
          ) {
            e.preventDefault();
            onSubmit();
          }
        }}
      />
      {!conversation && chapterError && <p className="field-hint composer-chapter-note" role="status">{chapterError}</p>}
      {children}
      {workbench?.attachments.length ? <div className="composer-attachments" aria-label="本课附件">{workbench.attachments.map(file => <span key={file.id}><Paperclip size={13} />{file.title}</span>)}</div> : null}
      {uploadError && <p className="inline-error" role="alert">{uploadError}</p>}
      <div className="composer-footer">
        <div>
          {conversation ? (
            <span className="agent-label">
              <Sparkles size={19} />
              启鸣 AI · {product === "导学案" ? "教学设计" : product}
            </span>
          ) : !workbench && (
            <button
              title={historyLabel}
              aria-label={historyLabel}
              className="icon-button"
              onClick={onHistory}
            >
              <History size={24} />
            </button>
          )}
          <button className="text-button" onClick={onOptimize} disabled={busy}>
            <SlidersHorizontal size={20} />
            优化提示
          </button>
        </div>
        <div className="composer-send-actions">
        {workbench?.onUpload && <>
          <input ref={attachmentInput} type="file" hidden accept=".txt,.md,.docx,.pdf" aria-label="上传附件文件" onChange={e => { if (e.target.files?.[0]) void uploadAttachment(e.target.files[0]); }} />
          <button className="icon-button" aria-label="上传附件" title="上传附件（TXT、Markdown、DOCX、PDF，最大20MB）" disabled={busy || uploading} onClick={() => attachmentInput.current?.click()}>
            {uploading ? <LoaderCircle className="spin" size={20} /> : <Paperclip size={20} />}
          </button>
        </>}
        <button
          className="send-button"
          aria-label={
            conversation
              ? product === "导学案"
                ? "提交修改"
                : `提交${product === "互动课件" ? "课件" : product}修改`
              : `生成${product}`
          }
          title="⌘ / Ctrl + Enter 提交"
          onClick={onSubmit}
          disabled={!canSubmit}
        >
          {busy ? (
            <LoaderCircle className="spin" size={23} />
          ) : (
            <ArrowUp size={26} />
          )}
        </button>
        </div>
      </div>
    </div>
  );
}

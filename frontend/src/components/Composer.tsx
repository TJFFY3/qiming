import type { ReactNode } from "react";
import {
  ArrowUp,
  BookOpen,
  History,
  SlidersHorizontal,
  Sparkles,
  LoaderCircle,
} from "lucide-react";
import type { Settings } from "../api";
export default function Composer<
  T extends { chapter: string; period: string } = Settings,
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
  const chapters = [
    "第三节 氧化还原反应",
    "第二节 离子反应",
    "第一节 物质的分类及转化",
    "钠及其化合物",
  ];
  const periods = ["第一课时", "第二课时"];
  const canSubmit =
    !busy && !!settings.chapter.trim() && (!conversation || !!prompt.trim());
  return (
    <div className={"composer " + (conversation ? "compact" : "")}>
      {!conversation && (
        <div className="sentence">
          <span>基于</span>
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
      {children}
      <div className="composer-footer">
        <div>
          {conversation ? (
            <span className="agent-label">
              <Sparkles size={19} />
              启鸣 AI · {product === "导学案" ? "教学设计" : product}
            </span>
          ) : (
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
  );
}

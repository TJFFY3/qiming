import {
  ArrowUp,
  BookOpen,
  History,
  SlidersHorizontal,
  Sparkles,
  LoaderCircle,
} from "lucide-react";
import type { Settings } from "../api";
export default function Composer({
  settings,
  onSettings,
  prompt,
  onPrompt,
  onSubmit,
  onOptimize,
  onHistory,
  busy,
  conversation = false,
}: {
  settings: Settings;
  onSettings: (s: Settings) => void;
  prompt: string;
  onPrompt: (v: string) => void;
  onSubmit: () => void;
  onOptimize: () => void;
  onHistory: () => void;
  busy: boolean;
  conversation?: boolean;
}) {
  const chapters = [
    "第三节 氧化还原反应",
    "第二节 离子反应",
    "第一节 物质的分类及转化",
    "钠及其化合物",
  ];
  const periods = ["第一课时", "第二课时", "第三课时", "复习课"];
  const widest = (values: string[]) =>
    values.reduce((a, b) => (a.length >= b.length ? a : b), "");
  return (
    <div className={"composer " + (conversation ? "compact" : "")}>
      {!conversation && (
        <div className="sentence">
          <span>基于</span>
          <label className="chapter-chip">
            <BookOpen size={23} />
            <span className="suggestion-input">
              <span className="suggestion-size" aria-hidden="true">
                {widest([...chapters, settings.chapter])}
              </span>
              <input
                aria-label="章节 / 知识点"
                list="chapters"
                value={settings.chapter}
                maxLength={200}
                onChange={(e) =>
                  onSettings({ ...settings, chapter: e.target.value })
                }
              />
            </span>
          </label>
          <datalist id="chapters">
            {chapters.map((chapter) => (
              <option key={chapter}>{chapter}</option>
            ))}
          </datalist>
          <span>生成</span>
          <label className="period-chip">
            <select
              aria-label="课时"
              value={settings.period}
              onChange={(e) =>
                onSettings({ ...settings, period: e.target.value })
              }
            >
              {!periods.includes(settings.period) && (
                <option value={settings.period}>{settings.period}</option>
              )}
              {periods.map((period) => (
                <option key={period} value={period}>
                  {period}
                </option>
              ))}
            </select>
          </label>
          <span>导学案</span>
        </div>
      )}
      <textarea
        className={
          prompt.includes("【优化提示】") ? "optimization-prompt" : undefined
        }
        aria-label={conversation ? "继续修改导学案" : "备课要求"}
        value={prompt}
        maxLength={8000}
        onChange={(e) => onPrompt(e.target.value)}
        placeholder={
          conversation
            ? "继续对话，随时调整这节课的设计，例如：增加互动环节…"
            : "例如：以生活情境导入，安排小组探究，突出重点和易错点…"
        }
        onKeyDown={(e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !busy) {
            e.preventDefault();
            onSubmit();
          }
        }}
      />
      <div className="composer-footer">
        <div>
          {conversation ? (
            <span className="agent-label">
              <Sparkles size={19} />
              启鸣 AI · 教学设计
            </span>
          ) : (
            <button
              title="历史备课"
              aria-label="历史备课"
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
          aria-label={conversation ? "提交修改" : "生成导学案"}
          title="⌘ / Ctrl + Enter 提交"
          onClick={onSubmit}
          disabled={
            busy || !settings.chapter.trim() || (conversation && !prompt.trim())
          }
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

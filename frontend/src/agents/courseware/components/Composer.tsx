import SharedComposer from "../../../components/Composer";
import type { CoursewareSettings } from "../domain/types";
export default function Composer({
  settings,
  onSettings,
  prompt,
  onPrompt,
  onOptimize,
  onHistory,
  onSubmit,
  busy,
  conversation = false,
  allowFullRevision,
  onFullRevision,
}: {
  settings: CoursewareSettings;
  onSettings: (s: CoursewareSettings) => void;
  prompt: string;
  onPrompt: (s: string) => void;
  onOptimize: () => void;
  onHistory: () => void;
  onSubmit: () => void;
  busy: boolean;
  conversation?: boolean;
  allowFullRevision: boolean;
  onFullRevision: (v: boolean) => void;
}) {
  return (
    <>
      <SharedComposer
        settings={settings}
        onSettings={onSettings}
        prompt={prompt}
        onPrompt={onPrompt}
        onOptimize={onOptimize}
        onHistory={onHistory}
        onSubmit={onSubmit}
        busy={busy}
        conversation={conversation}
        product="互动课件"
        chapterLabel="课件章节"
        periodLabel="课件课时"
        historyLabel="课件历史"
        promptLabel={conversation ? "继续修改课件" : "课件要求"}
        placeholder={
          conversation
            ? "例如：将第 3 页改为小组讨论，保留其他页面…"
            : "例如：设计 15 页课件，加入 3 个课堂互动环节，风格简洁清晰…"
        }
      >
        <div className="composer-options">
          <label>
            课件格式
            <select
              aria-label="课件格式"
              value={settings.format}
              onChange={() => {}}
              disabled={busy}
            >
              <option>传统 PPT</option>
            </select>
          </label>
          {conversation && (
            <label>
              修改方式
              <select
                aria-label="课件修改方式"
                disabled={busy}
                value={allowFullRevision ? "structure" : "pages"}
                onChange={(e) => onFullRevision(e.target.value === "structure")}
              >
                <option value="pages">局部修改（保留其他页）</option>
                <option value="structure">调整页数与结构</option>
              </select>
            </label>
          )}
        </div>
      </SharedComposer>
    </>
  );
}

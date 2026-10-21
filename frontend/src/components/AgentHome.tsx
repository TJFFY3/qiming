import {
  FileText,
  Presentation,
  ListChecks,
  History,
  Library,
  Paperclip,
  Sparkles,
  ChevronRight,
} from "lucide-react";
import brandLogo from "../assets/logo-left.svg";
export type AgentKind = "guide" | "courseware" | "practice";
const agents = [
  { id: "guide", name: "导学案", Icon: FileText },
  { id: "courseware", name: "互动课件", Icon: Presentation },
  { id: "practice", name: "限时练习", Icon: ListChecks },
] as const;

export function AgentHomeHeader({
  ready,
  onNew,
  onHistory,
  historyLabel = "历史备课",
}: {
  ready: boolean;
  onNew: () => void;
  onHistory: () => void;
  historyLabel?: string;
}) {
  return (
    <header className="site-header">
      <button className="brand" onClick={onNew} aria-label="返回首页">
        <img className="brand-logo" src={brandLogo} alt="品牌标识" />
      </button>
      <div className="header-actions">
        <span className="connection">
          <i className={ready ? "online" : ""} />
          {ready ? "服务已连接" : "本地工作台"}
        </span>
        <button
          className="icon-button"
          aria-label={historyLabel}
          onClick={onHistory}
        >
          <History size={19} />
        </button>
      </div>
    </header>
  );
}
export function AgentHero({
  active,
  onChange,
}: {
  active: AgentKind;
  onChange: (kind: AgentKind) => void;
}) {
  return (
    <section className="hero">
      <div className="eyebrow">
        <span />
        让每一节课，都有好设计
      </div>
      <h1>
        <span>启鸣 AI</span>，帮你备课
      </h1>
      <div className="product-tabs" role="tablist" aria-label="备课产物">
        {agents.map(({ id, name, Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={active === id}
            className={active === id ? "active" : undefined}
            onClick={() => onChange(id)}
          >
            <Icon size={22} />
            {name}
          </button>
        ))}
      </div>
    </section>
  );
}
export function LessonToolbar<T extends { edition: string; grade: string }>({
  settings,
  onSettings,
  onResources,
  busy = false,
  prefix = "",
  uploadCount = 0,
}: {
  settings: T;
  onSettings: (value: T) => void;
  onResources: () => void;
  busy?: boolean;
  prefix?: string;
  uploadCount?: number;
}) {
  return (
    <div className="resource-toolbar">
      <div>
        <button className="text-button library-button" onClick={onResources}>
          <Library size={20} />
          资料库
        </button>
        <button className="text-button" onClick={onResources}>
          <Paperclip size={20} />
          上传资源{uploadCount ? `（${uploadCount}）` : ""}
        </button>
      </div>
      <div className="lesson-context">
        <input
          aria-label={prefix + "教材版本"}
          maxLength={200}
          value={settings.edition}
          disabled={busy}
          onChange={(e) => onSettings({ ...settings, edition: e.target.value })}
        />
        <span>·</span>
        <select
          aria-label={prefix + "年级"}
          value={settings.grade}
          disabled={busy}
          onChange={(e) => onSettings({ ...settings, grade: e.target.value })}
        >
          <option>高一</option>
          <option>高二</option>
          <option>高三</option>
        </select>
      </div>
    </div>
  );
}
export function AppliedOptions({
  optimized,
  onOptimize,
  hint,
}: {
  optimized: boolean;
  onOptimize: () => void;
  hint: string;
}) {
  return (
    <div className="workspace-bottom">
      {optimized ? (
        <button className="applied-options" onClick={onOptimize}>
          <Sparkles size={14} />
          已填入优化要求
          <ChevronRight size={13} />
        </button>
      ) : (
        <span>{hint}</span>
      )}
    </div>
  );
}
export function AgentHomeFooter() {
  return (
    <footer className="home-footer">
      <span className="footer-line" />
      <Sparkles size={14} />
      <span>把备课的时间，还给教学的思考</span>
      <span className="footer-line" />
    </footer>
  );
}

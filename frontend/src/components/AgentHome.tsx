import { useEffect, useState } from "react";
import { api } from "../agents/study-guide/services/api";
import { subjectLessons } from "../subjects";
import { useWorkbench } from "./AgentWorkbench";
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
  const workbench = useWorkbench();
  if (workbench) return null;
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
        <span>Fast AI</span>，帮你备课
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
export function LessonToolbar<T extends { edition?: string; grade?: string; subject?: string; options?: object }>({
  settings,
  onSettings,
  onResources,
  busy = false,
  prefix = "",
  uploadCount = 0,
  inline = false,
}: {
  settings: T;
  onSettings: (value: T) => void;
  onResources: () => void;
  busy?: boolean;
  prefix?: string;
  uploadCount?: number;
  inline?: boolean;
}) {
  const workbench = useWorkbench();
  const [subjects, setSubjects] = useState(Object.keys(subjectLessons));
  useEffect(() => {
    let active = true;
    api<{subjects: string[]}>("/library/subjects").then(data => {
      const available = data.subjects?.filter(subject => subjectLessons[subject]);
      if (active && available?.length) setSubjects(available);
    }).catch(() => { /* 目录暂不可用时仍可编辑；生成端会校验学科与知识库映射。 */ });
    return () => { active = false; };
  }, []);
  return (
    <div className={inline ? "composer-lesson-fields" : "resource-toolbar"}>
      {!inline && <div>
        {!workbench && <button className="text-button library-button" onClick={onResources}>
          <Library size={20} />
          资料库
        </button>}
        {!workbench && <button className="text-button" onClick={onResources}>
          <Paperclip size={20} />
          上传资源{uploadCount ? `（${uploadCount}）` : ""}
        </button>}
      </div>}
      <div className="lesson-context">

        <select
          aria-label={prefix + "年级"}
          value={settings.grade || "高一"}
          disabled={busy}
          onChange={(e) => onSettings({ ...settings, grade: e.target.value })}
        >
          <option>高一</option>
          <option>高二</option>
          <option>高三</option>
        </select>
        <select aria-label={prefix + "学科"} value={settings.subject || "化学"} disabled={busy}
          onChange={e => {
            onSettings({...settings, subject:e.target.value, chapter:"", ...subjectLessons[e.target.value], options:{...settings.options,focus:["按本课安排（默认）"],extra:""}});
            workbench?.locateLibrary(e.target.value);
          }}>
          {Object.keys(subjectLessons).filter(subject => subjects.includes(subject) || subject === (settings.subject || "化学")).map(subject => <option key={subject}>{subject}</option>)}
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

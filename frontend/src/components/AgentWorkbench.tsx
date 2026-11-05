/** 三个 Agent 共用的工作台：左侧菜单，中间任务对话，右侧文件预览。 */
import { createContext, useCallback, useContext, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { BookOpen, FileText, History, Library, ListChecks, LoaderCircle, Menu, MessageSquare, Plus, Presentation, Sparkles, PanelRightClose, PanelRightOpen } from "lucide-react";
import brandLogo from "../assets/logo-left.svg";

type AgentKind = "guide" | "courseware" | "practice";
const agents = [
  { id: "guide", name: "导学案", Icon: FileText },
  { id: "courseware", name: "互动课件", Icon: Presentation },
  { id: "practice", name: "限时练习", Icon: ListChecks },
] as const;

type LibraryTarget = {subject: string; chapter?: string; requestId: number};

type WorkbenchContextValue = {
  previewTarget: HTMLDivElement | null;
  headerTarget: HTMLDivElement | null;
  sidebarTarget: HTMLDivElement | null;
  menuOpen: boolean;
  setPanelOpen: (value: boolean) => void;
  setHasPreview: (value: boolean) => void;
  showPreview: () => void;
  showChat: () => void;
  libraryTarget: LibraryTarget | null;
  locateLibrary: (subject: string, chapter?: string) => void;
  resolveLibraryChapter: (requestId: number, chapter: string) => void;
  onUpload?: (file: File, category: string) => Promise<void>;
  attachments: { id: string; title: string }[];
};
const WorkbenchContext = createContext<WorkbenchContextValue | null>(null);
export const useWorkbench = () => useContext(WorkbenchContext);

/** 将任务进度和预览挂载到同一工作台的右栏，Agent 切换不会串用容器。 */
export function WorkbenchPreview({ children }: { children: ReactNode }) {
  const workbench = useWorkbench();
  const target = workbench?.previewTarget;
  const register = workbench?.setHasPreview;
  useEffect(() => {
    if (!target || !register) return;
    register(true);
    return () => register(false);
  }, [target, register]);
  if (!workbench) return children;
  return target ? createPortal(children, target) : null;
}

export default function AgentWorkbench({
  agent, onResources, onHistory, onNew, onHome,
  ready, busy, job, onUpload, attachments = [], historyLabel = "历史备课", children,
}: {
  onUpload?: (file: File, category: string) => Promise<void>;
  attachments?: { id: string; title: string }[];
  agent: AgentKind;
  onAgentChange: (agent: AgentKind) => void;
  onResources: () => void;
  onHistory: () => void;
  onNew: () => void;
  onHome: () => void;
  ready: boolean;
  busy: boolean;
  job?: { status: string; stages: { label: string }[] } | null;
  historyLabel?: string;
  children: ReactNode;
}) {
  const [libraryTarget, setLibraryTarget] = useState<LibraryTarget | null>(null);
  const libraryRequestId = useRef(0);
  const [headerTarget, setHeaderTarget] = useState<HTMLDivElement | null>(null);
  const workbenchRef = useRef<HTMLDivElement>(null);
  const dragPointer = useRef<number | null>(null);
  const [resizing, setResizing] = useState(false);
  const [previewShare, setPreviewShare] = useState(.55);
  const resizeAt = (clientX: number) => {
    const root = workbenchRef.current;
    if (!root) return;
    const bounds = root.getBoundingClientRect();
    const sidebar = root.querySelector(".workbench-sidebar")?.getBoundingClientRect().width || 0;
    const available = bounds.width - sidebar - 6;
    if (available <= 580) return;
    const width = Math.max(300, Math.min(available - 280, bounds.right - clientX - 3));
    setPreviewShare(Math.max(.2, Math.min(.8, width / available)));
  };
  const [previewTarget, setPreviewTarget] = useState<HTMLDivElement | null>(null);
  const [sidebarTarget, setSidebarTarget] = useState<HTMLDivElement | null>(null);
  const [panelOpen, updatePanelOpen] = useState(false);
  const [hasPreview, setHasPreview] = useState(false);
  const [pane, setPane] = useState<"chat" | "preview">("chat");
  const [menuOpen, setMenuOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(true);
  // 知识库、历史和来源面板在右侧展开，窄屏自动切到该区域。
  const setPanelOpen = useCallback((open: boolean) => { updatePanelOpen(open); if (open) { setPreviewOpen(true); setPane("preview"); setMenuOpen(false); } }, []);
  const showChat = useCallback(() => { setPane("chat"); setMenuOpen(false); updatePanelOpen(false); }, []);
  const showPreview = useCallback(() => { setPreviewOpen(true); setPane("preview"); setMenuOpen(false); updatePanelOpen(false); }, []);
  const hidePreview = () => { dragPointer.current=null; setResizing(false); setPreviewOpen(false); setPane("chat"); updatePanelOpen(false); };
  const startNew = () => { setLibraryTarget(null); setPane("chat"); setMenuOpen(false); onNew(); };
  const product = agents.find((item) => item.id === agent)!.name;
  const openPanel = (action: () => void) => { setPreviewOpen(true); setPane("preview"); setMenuOpen(false); action(); };
  const locateLibrary = (subject: string, chapter?: string) => {
    setLibraryTarget({subject,chapter,requestId:++libraryRequestId.current});
    setPanelOpen(true);
    onResources();
  };
  // 异步目录结果只补全定位目标，不重新打开已关闭的资料库或覆盖历史任务面板。
  const resolveLibraryChapter = (requestId: number, chapter: string) => {
    setLibraryTarget(current => current?.requestId === requestId && !current.chapter ? {...current,chapter} : current);
  };
  const previewToggle = <button className="icon-button" aria-label={previewOpen ? "隐藏文件预览" : "显示文件预览"} title={previewOpen ? "隐藏文件预览" : "显示文件预览"} aria-expanded={previewOpen} onClick={previewOpen ? hidePreview : showPreview}>
    {previewOpen ? <PanelRightClose size={19} /> : <PanelRightOpen size={19} />}
  </button>;
  return (
    <WorkbenchContext.Provider value={{ libraryTarget, locateLibrary, resolveLibraryChapter, headerTarget, previewTarget, sidebarTarget, menuOpen: panelOpen, onUpload, attachments, setPanelOpen, setHasPreview, showPreview, showChat }}>
      <div ref={workbenchRef} className="agent-workbench" data-resizing={resizing} style={{"--main-share":`${1-previewShare}fr`, "--preview-share":`${previewShare}fr`} as CSSProperties} data-preview={previewOpen} data-pane={pane} data-panel={panelOpen} data-menu={menuOpen}>
        <div className="workbench-mobile-toolbar">
          <button className="icon-button" aria-label="展开工作台菜单" aria-expanded={menuOpen} onClick={() => setMenuOpen(!menuOpen)}><Menu size={20} /></button>
          <button className={pane === "chat" ? "active" : ""} onClick={() => { setPane("chat"); setMenuOpen(false); }}><MessageSquare size={16} />任务对话</button>
          <button className={pane === "preview" ? "active" : ""} aria-label="查看文件预览" onClick={() => { showPreview(); setMenuOpen(false); }}><FileText size={16} />文件预览</button>
        </div>
        <aside className="workbench-sidebar" aria-label="工作台菜单">
          <button className="workbench-brand" aria-label="启鸣 AI 首页" onClick={onHome}><img src={brandLogo} alt="品牌标识" /></button>
          <button className="workbench-new" onClick={startNew} disabled={busy}><Plus size={18} />新建任务</button>
          <div className="workbench-library-nav">
            <button aria-label="资料库" onClick={() => openPanel(onResources)}><Library size={18} /><span>知识库<small>资料库与本课资源</small></span></button>
            <button aria-label={historyLabel} onClick={() => openPanel(onHistory)}><History size={18} /><span>历史任务<small>已生成的文件与版本</small></span></button>
          </div>
          <footer className="workbench-sidebar-footer"><span className={ready ? "workbench-online" : "workbench-offline"} /><span>{ready ? "服务已连接" : "本地工作台"}</span><BookOpen size={14} /></footer>
        </aside>
        <header className="workbench-shared-header" aria-label="工作台头部">
          <div ref={setHeaderTarget} className="workbench-header-content" />
          <div className="workbench-global-controls">{previewToggle}</div>
        </header>
        <div className="workbench-main">
          {children}
        </div>
        <div className="workbench-resizer" hidden={!previewOpen} role="separator" aria-label="调整预览区域宽度" aria-orientation="vertical" aria-valuemin={20} aria-valuemax={80} aria-valuenow={Math.round(previewShare*100)} tabIndex={previewOpen ? 0 : -1}
          onPointerDown={e => { if (e.button !== 0) return; dragPointer.current=e.pointerId; setResizing(true); e.currentTarget.setPointerCapture?.(e.pointerId); }}
          onPointerMove={e => { if (dragPointer.current === e.pointerId) resizeAt(e.clientX); }}
          onPointerUp={() => { dragPointer.current=null; setResizing(false); }}
          onPointerCancel={() => { dragPointer.current=null; setResizing(false); }}
          onLostPointerCapture={() => { dragPointer.current=null; setResizing(false); }}
          onDoubleClick={() => setPreviewShare(.55)}
          onKeyDown={e => {
            if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return;
            e.preventDefault();
            setPreviewShare(value => e.key === 'Home' ? .2 : e.key === 'End' ? .8 : Math.max(.2, Math.min(.8, value + (e.key === 'ArrowLeft' ? .05 : -.05))));
          }} />
        <aside className="workbench-preview" aria-label="文件预览">

          <div className="workbench-preview-body">
            <div ref={setSidebarTarget} className="workbench-panel-slot" hidden={!panelOpen} />
            <div hidden={panelOpen}>
            {!hasPreview && <div className="workbench-preview-empty">
              <div className="workbench-file-icon">{busy ? <LoaderCircle size={32} className="spin" /> : <FileText size={34} />}</div>
              <h2>{busy ? `正在生成${product}` : "你的教学文件将在这里呈现"}</h2>
              <p>{busy ? job?.stages.at(-1)?.label || "任务已提交，正在准备内容…" : "在中间描述本课要求，生成后可在此预览、切换版本并下载文件。"}</p>
              <span><Sparkles size={14} />{product} · 独立文件预览区</span>
            </div>}
            <div ref={setPreviewTarget} className="workbench-preview-slot" />
            </div>
          </div>
        </aside>
      </div>
    </WorkbenchContext.Provider>
  );
}

import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useWorkbench } from "./AgentWorkbench";
import { X } from "lucide-react";
export default function Modal({
  title,
  onClose,
  children,
  className = "",
  placement = "center",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
  placement?: "center" | "sidebar";
}) {
  const workbench = useWorkbench();
  const docked = placement === "sidebar" && !!workbench;
  const dockTarget = workbench?.sidebarTarget;
  const setPanelOpen = workbench?.setPanelOpen;
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const wasMenuOpen = useRef(false);
  useEffect(() => {
    // 右侧切回文件或被收起时关闭资料面板，保证再次点击菜单能重新打开。
    if (docked && wasMenuOpen.current && !workbench?.menuOpen) closeRef.current();
    wasMenuOpen.current = !!workbench?.menuOpen;
  }, [docked, workbench?.menuOpen]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const bodyOverflow = document.body.style.overflow;
    if (!docked) document.body.style.overflow = "hidden";
    if (docked && dockTarget) setPanelOpen?.(true);
    ref.current?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (!docked && e.key === "Tab") {
        const items = ref.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),textarea,select,a[href],[tabindex="0"]',
        );
        if (!items?.length) return;
        const first = items[0],
          last = items[items.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === ref.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      if (!docked) document.body.style.overflow = bodyOverflow;
      if (docked && dockTarget) setPanelOpen?.(false);
      previous?.focus();
    };
  }, [docked, dockTarget, setPanelOpen]);
  const content = (
    <div ref={ref} tabIndex={-1} role="dialog" aria-modal={docked ? undefined : true}
      aria-label={title} className={"modal " + (docked ? "workbench-docked-panel " : "") + className}>
      <div className="modal-header">
        <h2>{title}</h2>
        <button className="icon-button" aria-label="关闭" onClick={onClose}><X /></button>
      </div>
      {children}
    </div>
  );
  if (docked) return dockTarget ? createPortal(content, dockTarget) : null;
  return (
    <div className="modal-backdrop" onMouseDown={(e) => {
      if (e.target === e.currentTarget) onClose();
    }}>{content}</div>
  );
}

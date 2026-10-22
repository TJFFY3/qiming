import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export default function CoursewareImage({
  src,
  caption,
}: {
  src: string;
  caption?: string;
}) {
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const close = useRef<HTMLButtonElement>(null);
  const label = caption || "课件原图";
  useEffect(() => {
    setFailed(false);
    setExpanded(false);
  }, [src]);
  useEffect(() => {
    if (!expanded) return;
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape" || event.key === "Tab") {
        event.preventDefault();
        event.stopPropagation();
        if (event.key === "Escape") setExpanded(false);
        else close.current?.focus();
      }
    };
    window.addEventListener("keydown", key, true);
    return () => {
      window.removeEventListener("keydown", key, true);
      previous?.focus();
    };
  }, [expanded]);
  return (
    <>
      <figure className="cw-original-image">
        {failed ? (
          <div role="status">图片加载失败，请稍后重试。</div>
        ) : (
          <button
            type="button"
            aria-label={`放大图片：${label}`}
            onClick={() => setExpanded(true)}
          >
            <img src={src} alt={label} onError={() => setFailed(true)} />
          </button>
        )}
        {caption && <figcaption>{caption}</figcaption>}
      </figure>
      {expanded &&
        createPortal(
          <div
            className="cw-image-viewer"
            role="dialog"
            aria-modal="true"
            aria-label="课件图片"
            onClick={() => setExpanded(false)}
          >
            <button
              ref={close}
              type="button"
              aria-label="关闭图片"
              onClick={() => setExpanded(false)}
            >
              关闭
            </button>
            <figure onClick={(event) => event.stopPropagation()}>
              <img src={src} alt={label} />
              {caption && <figcaption>{caption}</figcaption>}
            </figure>
          </div>,
          document.body,
        )}
    </>
  );
}

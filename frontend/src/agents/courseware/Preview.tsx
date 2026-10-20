import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  MonitorPlay,
  Presentation,
  ExternalLink,
  CheckCircle2,
  X,
} from "lucide-react";
import { fileUrl } from "./api";
import type { RichText, Run, Slide, Version } from "./types";
function formula(text: string): Run[] {
  const result: Run[] = [];
  const parts = text.split(/(\[[^\[\]]+\])/g);
  for (const part of parts) {
    if (!part.startsWith("[") || !part.endsWith("]")) {
      result.push({ text: part });
      continue;
    }
    const value = part.slice(1, -1);
    const charge = value.match(/(?:\^(\d*[+-])|([+-]))$/);
    const body = charge ? value.slice(0, -charge[0].length) : value;
    for (const piece of body.split(/(\d+)/g))
      if (piece) result.push({ text: piece, sub: /^\d+$/.test(piece) });
    if (charge) result.push({ text: charge[1] || charge[2], sup: true });
  }
  return result;
}
export function Rich({ value }: { value: RichText }) {
  const runs =
    typeof value === "string"
      ? formula(value)
      : value.flatMap((run) =>
          run.condition || run.isotope
            ? [run]
            : formula(run.text).map((part) => ({
                ...run,
                ...part,
                sub: part.sub || run.sub,
                sup: part.sup || run.sup,
              })),
        );
  return (
    <>
      {runs.map((r, i) => {
        let content: React.ReactNode = r.text;
        if (r.condition)
          content = (
            <span className="cw-condition">
              <small>{r.text}</small>
              <span className="cw-reaction-equals" aria-label="反应等号" />
            </span>
          );
        else if (r.isotope)
          content = (
            <span className="cw-isotope">
              <span>
                <sup>{r.isotope.mass}</sup>
                <sub>{r.isotope.atomic}</sub>
              </span>
              {r.text}
            </span>
          );
        else if (r.sup || r.charge) content = <sup>{content}</sup>;
        else if (r.sub) content = <sub>{content}</sub>;
        return (
          <span
            key={i}
            style={{
              fontWeight: r.bold ? "bold" : undefined,
              fontStyle: r.italic ? "italic" : undefined,
              textDecoration: r.underline ? "underline" : undefined,
            }}
          >
            {content}
          </span>
        );
      })}
    </>
  );
}
function SlideCanvas({ slide, index }: { slide: Slide; index: number }) {
  return (
    <div className="cw-slide" aria-label={`第 ${index + 1} 页：${slide.title}`}>
      <span className="cw-stage">{slide.stage}</span>
      <h2>
        <Rich value={slide.title} />
      </h2>
      <div className="cw-slide-body">
        {slide.paragraphs.map((p, i) => (
          <p key={i}>
            <Rich value={p} />
          </p>
        ))}
      </div>
      <span className="cw-slide-number">
        {String(index + 1).padStart(2, "0")}
      </span>
    </div>
  );
}
export default function Preview({
  sid,
  version,
  onSources,
}: {
  sid: string;
  version: Version;
  onSources?: () => void;
}) {
  const [index, setIndex] = useState(0),
    [presenting, setPresenting] = useState(false);
  const count = version.content.slides.length;
  useEffect(() => setIndex(0), [version.id]);
  useEffect(() => {
    if (!presenting) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const key = (e: KeyboardEvent) => {
      if (["ArrowRight", "ArrowLeft", " ", "Escape"].includes(e.key))
        e.preventDefault();
      if (e.key === "Escape") setPresenting(false);
      if (e.key === "ArrowRight" || e.key === " ")
        setIndex((i) => Math.min(count - 1, i + 1));
      if (e.key === "ArrowLeft") setIndex((i) => Math.max(0, i - 1));
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", key);
    };
  }, [presenting, count]);
  const slide = version.content.slides[Math.min(index, count - 1)];
  if (!slide) return null;
  return (
    <section className="document-card">
      <header className="document-toolbar">
        <span>
          <Presentation size={20} />
          互动课件 <b>{version.number}</b>
        </span>
        <div>
          {onSources && (
            <button className="text-button" onClick={onSources}>
              查看来源
              <ExternalLink size={14} />
            </button>
          )}
          <button
            className="button secondary small"
            onClick={() => setPresenting(true)}
          >
            <MonitorPlay size={16} />
            演示
          </button>
          <a
            className="button primary small"
            href={fileUrl(sid, version.id)}
            download
          >
            <Download size={16} />
            下载 PPTX
          </a>
        </div>
      </header>
      <div className="document-status">
        <span>
          <CheckCircle2 size={14} />
          结构检查通过
        </span>
        <span>{count} 页 · 原生可编辑 PPTX</span>
      </div>
      <h2 className="courseware-document-title">{version.content.title}</h2>
      <div className="cw-preview-layout">
        <nav className="cw-thumbnails" aria-label="课件页面">
          {version.content.slides.map((s, i) => (
            <button
              key={i}
              aria-current={i === index ? "page" : undefined}
              onClick={() => setIndex(i)}
            >
              <span>{String(i + 1).padStart(2, "0")}</span>
              <div>
                <strong>{s.title}</strong>
                <small>{s.stage}</small>
              </div>
            </button>
          ))}
        </nav>
        <div>
          <SlideCanvas slide={slide} index={index} />
          <div className="cw-page-controls">
            <button
              className="icon-button"
              aria-label="上一页"
              disabled={index === 0}
              onClick={() => setIndex((i) => i - 1)}
            >
              <ChevronLeft size={20} />
            </button>
            <span>
              {index + 1} / {count}
            </span>
            <button
              className="icon-button"
              aria-label="下一页"
              disabled={index === count - 1}
              onClick={() => setIndex((i) => i + 1)}
            >
              <ChevronRight size={20} />
            </button>
          </div>
          {slide.notes && (
            <details className="cw-notes">
              <summary>教师备注与答案</summary>
              <p>{slide.notes}</p>
            </details>
          )}
        </div>
      </div>
      <div className="cw-review-note">
        <strong>课件说明</strong>
        <p>{version.report.visual_review}</p>
        {[...version.report.source_issues, ...version.report.conflicts].map(
          (note, i) => (
            <p key={i}>{note}</p>
          ),
        )}
        {version.report.validation.warnings.map((w, i) => (
          <p key={"w" + i}>{w.message}</p>
        ))}
        <a href={fileUrl(sid, version.id, "report")} download>
          下载检查报告
        </a>
      </div>
      {presenting && (
        <div
          className="cw-presentation"
          role="dialog"
          aria-modal="true"
          aria-label="课件演示"
        >
          <div className="cw-presentation-bar">
            <button
              className="text-button"
              autoFocus
              onClick={() => setPresenting(false)}
            >
              <ArrowLeft size={18} />
              退出演示
            </button>
            <span>← → 翻页 · Esc 退出</span>
            <button
              aria-label="关闭演示"
              className="icon-button"
              onClick={() => setPresenting(false)}
            >
              <X size={22} />
            </button>
          </div>
          <SlideCanvas slide={slide} index={index} />
          <div className="cw-page-controls">
            <button
              aria-label="演示上一页"
              className="icon-button"
              disabled={index === 0}
              onClick={() => setIndex((i) => i - 1)}
            >
              <ChevronLeft />
            </button>
            <span>
              {index + 1} / {count}
            </span>
            <button
              aria-label="演示下一页"
              className="icon-button"
              disabled={index === count - 1}
              onClick={() => setIndex((i) => i + 1)}
            >
              <ChevronRight />
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

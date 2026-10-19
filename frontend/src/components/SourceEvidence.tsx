import { useEffect, useRef, useState } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ImageOff, LoaderCircle, ExternalLink } from "lucide-react";
import { convertSourceImage } from "../metafile";

function safeImageUrl(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}

function EvidenceImage({ src, alt }: { src?: string; alt?: string }) {
  const url = safeImageUrl(src);
  const [display, setDisplay] = useState(url);
  const [state, setState] = useState<"image" | "converting" | "failed">(
    "image",
  );
  const live = useRef(true);
  const attempted = useRef(false);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
    };
  }, []);
  const failed = () => {
    if (!url) return;
    if (attempted.current) {
      setState("failed");
      return;
    }
    attempted.current = true;
    setState("converting");
    void convertSourceImage(url)
      .then((result) => {
        if (live.current) {
          setDisplay(result);
          setState("image");
        }
      })
      .catch(() => {
        if (live.current) setState("failed");
      });
  };
  if (!url)
    return (
      <span className="evidence-image-error">
        图片链接不可用{alt ? `：${alt}` : ""}
      </span>
    );
  return (
    <span className="evidence-image">
      {state === "converting" ? (
        <span className="evidence-image-loading">
          <LoaderCircle className="spin" size={18} />
          正在加载图片…
        </span>
      ) : state === "failed" ? (
        <span className="evidence-image-error">
          <ImageOff size={20} />
          图片暂时无法显示
        </span>
      ) : (
        <a
          href={display}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="放大图片"
        >
          <img
            src={display}
            alt={alt || "知识库资料图片"}
            loading="lazy"
            decoding="async"
            referrerPolicy="no-referrer"
            onError={failed}
          />
        </a>
      )}
      <span className="evidence-image-caption">
        <span>{alt || "知识库图片"}</span>
        <a href={url} target="_blank" rel="noopener noreferrer">
          查看原图
          <ExternalLink size={12} />
        </a>
      </span>
    </span>
  );
}

export default function SourceEvidence({ text }: { text: string }) {
  return (
    <div className="source-evidence">
      <Markdown
        skipHtml
        remarkPlugins={[remarkGfm]}
        components={{
          img: ({ src, alt }) => (
            <EvidenceImage key={src} src={src} alt={alt} />
          ),
          a: ({ href, children }) => (
            <a
              href={safeImageUrl(href)}
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

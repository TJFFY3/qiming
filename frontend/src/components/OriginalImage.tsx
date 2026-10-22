import { useState } from "react";

export default function OriginalImage({
  src,
  caption,
}: {
  src: string;
  caption: string;
}) {
  const [failed, setFailed] = useState(false);
  return (
    <figure className="original-image">
      {failed ? (
        <div className="original-image-fallback" role="status">
          图片加载失败，请稍后重试。
        </div>
      ) : (
        <img
          src={src}
          alt={caption || "知识库原图"}
          onError={() => setFailed(true)}
        />
      )}
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}

// Office WMF/EMF images cannot be displayed by <img> natively.
// Convert only after native loading fails; ordinary images need no extra request.
const converted = new Map<string, Promise<string>>();
const MAX_BYTES = 8 * 1024 * 1024;

export function convertSourceImage(url: string): Promise<string> {
  const existing = converted.get(url);
  if (existing) return existing;
  const pending = (async () => {
    const response = await fetch(url, {
      credentials: "omit",
      referrerPolicy: "no-referrer",
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error("图片读取失败");
    if (Number(response.headers.get("content-length")) > MAX_BYTES)
      throw new Error("图片过大");
    const buffer = await response.arrayBuffer();
    if (buffer.byteLength > MAX_BYTES) throw new Error("图片过大");
    const { convertMetafileToDataUrl } = await import("emf-converter");
    const image = await convertMetafileToDataUrl(buffer, {
      maxWidth: 1600,
      maxHeight: 1200,
      maxCanvasDimension: 2048,
      maxRecords: 30000,
      ansiCodePage: 936,
      fontFamilyMap: {
        simsun: "Songti SC",
        宋体: "Songti SC",
        黑体: "PingFang SC",
      },
    });
    if (!image) throw new Error("图片格式暂不支持");
    return image;
  })();
  converted.set(url, pending);
  if (converted.size > 32) converted.delete(converted.keys().next().value!);
  void pending.catch(() => {
    if (converted.get(url) === pending) converted.delete(url);
  });
  return pending;
}

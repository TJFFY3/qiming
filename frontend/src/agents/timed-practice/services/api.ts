/** 【后端接口·限时练习】封装练习 HTTP 请求，不直接调用模型或知识库。 */
export const PREFIX = "/api/timed-practice";
export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(PREFIX + path, {
      ...init,
      headers:
        init?.body instanceof FormData
          ? init.headers
          : { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("无法连接限时练习服务，请确认后端已启动。");
  }
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "服务响应异常" }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : Array.isArray(data.detail)
          ? data.detail.map((d: { msg: string }) => d.msg).join("；")
          : "请求失败，请重试",
    );
  }
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, value: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(value) });
export const fileUrl = (sid: string, vid: string, kind: "paper" | "answers") =>
  `${PREFIX}/sessions/${sid}/versions/${vid}/files/${kind}`;
export const imageUrl = (sid: string, vid: string, imageId: string) =>
  `${PREFIX}/sessions/${encodeURIComponent(sid)}/versions/${encodeURIComponent(vid)}/images/${encodeURIComponent(imageId)}`;

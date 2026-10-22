/** 【后端接口·互动课件】封装 /api/courseware 请求，不直接调用模型或知识库。 */
export const PREFIX = "/api/courseware";
export class CoursewareApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
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
    throw new Error("无法连接课件服务，请确认后端已启动。");
  }
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "课件服务响应异常" }));
    throw new CoursewareApiError(
      Array.isArray(data.detail)
        ? data.detail.map((d: { msg: string }) => d.msg).join("；")
        : data.detail || "课件请求失败",
      response.status,
    );
  }
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const fileUrl = (sid: string, vid: string, kind = "pptx") =>
  `${PREFIX}/sessions/${encodeURIComponent(sid)}/versions/${encodeURIComponent(vid)}/files/${kind}`;

export const imageUrl = (sid: string, vid: string, imageId: string) =>
  `${PREFIX}/sessions/${encodeURIComponent(sid)}/versions/${encodeURIComponent(vid)}/images/${encodeURIComponent(imageId)}`;

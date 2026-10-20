export type Options = {
  scope: string;
  duration: string;
  tasks: string;
  difficulty: string;
  hints: string;
  focus: string[];
  extra: string;
};
export type Settings = {
  chapter: string;
  period: string;
  edition: string;
  grade: string;
  options: Options;
};
export const defaultOptions = (): Options => ({
  scope: "当前课时（默认）",
  duration: "按本课安排（默认）",
  tasks: "按本课安排（默认）",
  difficulty: "按本课安排（默认）",
  hints: "按本课安排（默认）",
  focus: ["按本课安排（默认）"],
  extra: "",
});
export const defaultSettings = (): Settings => ({
  chapter: "第三节 氧化还原反应",
  period: "第一课时",
  edition: "人教版 必修第一册",
  grade: "高一",
  options: defaultOptions(),
});
export type Source = {
  id: string;
  title: string;
  category: string;
  locator: string;
  evidence: string;
  verified: boolean;
  review_note?: string;
  score?: number;
};
export type Run = {
  text: string;
  sub?: boolean;
  sup?: boolean;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  charge?: boolean;
  condition?: boolean;
  isotope?: { mass: string | number; atomic: string | number };
};
export type RichText = string | Run[] | null;
export type Block =
  | { id: string; type: "paragraph"; content: RichText }
  | { id: string; type: "table"; headers: RichText[]; rows: RichText[][] };
export type Outline = {
  title: string;
  goals: RichText[];
  sections: { id: string; title: string; group?: string; blocks: Block[] }[];
  thinking?: RichText[];
  schedule_note?: string;
};
export type Version = {
  id: string;
  number: string;
  parent_id: string | null;
  change_kind: string;
  created_at: string;
  content_sha256: string;
  content: Outline;
  sources: Source[];
  report: {
    draft: boolean;
    source_issues: string[];
    review_required: string[];
    statistics: { content_tables: number; note_rows: number };
    validation: { passed: boolean };
  };
};
export type Job = {
  kind: "generation" | "revision";
  base_version_id?: string | null;
  id: string;
  session_id: string;
  status: "queued" | "running" | "completed" | "failed";
  stages: {
    index: number;
    label: string;
    status: string;
    started_at: string;
    ended_at?: string;
  }[];
  error: string | null;
  error_detail?: string | null;
  version_id: string | null;
  created_at: string;
};
export type Session = {
  id: string;
  settings: Settings;
  messages: {
    role: string;
    content: string;
    job_id?: string;
    version_id?: string;
  }[];
  resources: Source[];
  sources: Source[];
  versions: Version[];
  jobs: Job[];
};
export type SessionSummary = {
  id: string;
  settings: Settings;
  updated_at: string;
  version_count: number;
};
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch("/api" + path, {
      ...init,
      headers:
        init?.body instanceof FormData
          ? init.headers
          : { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("无法连接后端服务，请确认服务已启动。");
  }
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: "服务响应异常" }));
    const detail = Array.isArray(data.detail)
      ? data.detail.map((x: { msg: string }) => x.msg).join("；")
      : data.detail;
    throw new Error(
      typeof detail === "string" ? detail : "请求失败，请稍后重试",
    );
  }
  return response.json() as Promise<T>;
}
export const post = <T>(path: string, value: unknown) =>
  api<T>(path, { method: "POST", body: JSON.stringify(value) });
export const fileUrl = (sid: string, vid: string, kind = "outline") =>
  `/api/sessions/${sid}/versions/${vid}/files/${kind}`;

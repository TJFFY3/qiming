export const DEFAULT = "按本课安排（默认）";
export type AgentId = "guide" | "courseware" | "practice";
export type Options = {
  duration: string;
  score: string;
  questions: string;
  difficulty: string;
  origin: string;
  focus: string[];
  extra: string;
};
export const defaultOptions = (): Options => ({
  duration: DEFAULT,
  score: DEFAULT,
  questions: DEFAULT,
  difficulty: DEFAULT,
  origin: DEFAULT,
  focus: [DEFAULT],
  extra: "",
});
export type Settings = {
  chapter: string;
  period: string;
  edition: string;
  grade: string;
  options: Options;
};
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
};
export type Run = {
  text: string;
  sub?: boolean;
  sup?: boolean;
  charge?: boolean;
  condition?: boolean;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  isotope?: { mass: number; atomic: number };
};
export type RichText = string | Run[];
export type QuestionImage = {
  image_id: string;
  caption: string;
  placement:
    | "stem"
    | "option_A"
    | "option_B"
    | "option_C"
    | "option_D"
    | "answer"
    | "explanation";
};
export type Question = {
  stem: RichText;
  options?: RichText[];
  answer: RichText;
  explanation: RichText;
  score: number;
  minutes: number;
  difficulty: string;
  source_ids: string[];
  origin: "original" | "adapted" | "new";
  work_lines: number;
  images?: QuestionImage[];
};
export type Content = {
  title: string;
  duration: number;
  total_score: number;
  choice: Question[];
  written: Question[];
  optional: Question[];
  source_gaps: string[];
  conflicts: string[];
};
export type Version = {
  id: string;
  number: string;
  parent_id: string | null;
  created_at: string;
  content: Content;
  sources: Source[];
  report: {
    draft: boolean;
    source_issues: string[];
    review_required: string[];
    validation: { passed: boolean };
  };
};
export type Job = {
  id: string;
  session_id: string;
  status: "queued" | "running" | "completed" | "failed";
  kind: "generation" | "revision";
  base_version_id?: string;
  stages: { label: string; status: string }[];
  error?: string;
  source_issues?: string[];
  version_id?: string;
  effective_requirements?: { duration: number; total_score: number };
};
export type Session = {
  id: string;
  settings: Settings;
  messages: { role: string; content: string; version_id?: string }[];
  resources: Source[];
  sources: Source[];
  versions: Version[];
  jobs: Job[];
};
export type Summary = {
  id: string;
  settings: Settings;
  updated_at: string;
  version_count: number;
};

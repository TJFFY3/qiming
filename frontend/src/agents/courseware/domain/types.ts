export const DEFAULT = "按本课安排（默认）";
export type CoursewareOptions = {
  scope: string;
  duration: string;
  pages: string;
  exercises: string;
  teaching: string;
  focus: string[];
  extra: string;
};
export const defaultOptions = (): CoursewareOptions => ({
  scope: "当前课时（默认）",
  duration: DEFAULT,
  pages: DEFAULT,
  exercises: DEFAULT,
  teaching: DEFAULT,
  focus: [DEFAULT],
  extra: "",
});
export type CoursewareSettings = {
  chapter: string;
  period: string;
  edition: string;
  grade: string;
  format: "传统 PPT";
  options: CoursewareOptions;
};
export const defaultSettings = (): CoursewareSettings => ({
  chapter: "第三节 氧化还原反应",
  period: "第一课时",
  edition: "人教版 必修第一册",
  grade: "高一",
  format: "传统 PPT",
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
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  charge?: boolean;
  condition?: boolean;
  isotope?: { mass: number; atomic: number };
};
export type RichText = string | Run[];
export type Slide = {
  title: string;
  stage: string;
  paragraphs: RichText[];
  notes?: string;
  image_id?: string | null;
  image_caption?: string;
};
export type Deck = {
  title: string;
  slides: Slide[];
  source_gaps?: string[];
  conflicts?: string[];
};
export type Version = {
  id: string;
  number: string;
  parent_id: string | null;
  created_at: string;
  content: Deck;
  sources: Source[];
  report: {
    draft: boolean;
    page_count: number;
    source_issues: string[];
    conflicts: string[];
    visual_review: string;
    validation: { passed: boolean; warnings: { message: string }[] };
  };
};
export type Job = {
  id: string;
  session_id: string;
  status: "queued" | "running" | "completed" | "failed";
  kind: "generation" | "revision";
  stages: { label: string; status: string }[];
  error: string | null;
  version_id: string | null;
};
export type Session = {
  id: string;
  settings: CoursewareSettings;
  resources: Source[];
  sources: Source[];
  versions: Version[];
  messages: {
    role: string;
    content: string;
    version_id?: string;
    job_id?: string;
  }[];
  jobs: Job[];
};
export type SessionSummary = {
  id: string;
  settings: CoursewareSettings;
  updated_at: string;
  version_count: number;
};
export type LibraryData = {
  documents: {
    id: string;
    title: string;
    dataset_name: string;
    kind: string;
    chunks: Source[];
  }[];
  chunk_count: number;
  synced_at: string | null;
};

// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "../App";
import { defaultSettings as guideSettings } from "../agents/study-guide/services/api";
import { defaultSettings as courseSettings } from "../agents/courseware/domain/types";
import { defaultSettings as practiceSettings } from "../agents/timed-practice/domain/types";
afterEach(() => {
  cleanup();
  localStorage.clear();
  window.history.replaceState(null, "", "#guide");
  vi.restoreAllMocks();
});
const agents = [
  {
    id: "guide",
    product: "导学案",
    key: "qiming-session",
    settings: guideSettings,
  },
  {
    id: "courseware",
    product: "互动课件",
    key: "qiming-courseware-session",
    settings: courseSettings,
  },
  {
    id: "practice",
    product: "限时练习",
    key: "qiming-practice-session",
    settings: practiceSettings,
  },
] as const;
function fixture(
  agent: (typeof agents)[number],
  status = "failed",
  withVersions = false,
) {
  const makeVersion = (id: string) => ({
    id,
    number: id === "v1" ? "v001" : "v002",
    parent_id: id === "v1" ? null : "v1",
    created_at: new Date().toISOString(),
    change_kind: "首次生成",
    content_sha256: id,
    sources: [],
    content:
      agent.id === "guide"
        ? { title: "导学案" + id, goals: ["学习目标"], sections: [] }
        : agent.id === "courseware"
          ? {
              title: "课件" + id,
              slides: [
                {
                  title: "课件" + id,
                  stage: "启",
                  paragraphs: ["探究氧化还原反应"],
                  notes: "答案提示",
                },
                {
                  title: "课堂讨论",
                  stage: "析",
                  paragraphs: ["比较反应前后化合价"],
                },
              ],
            }
          : {
              title: "练习" + id,
              duration: 35,
              total_score: 100,
              choice: [
                {
                  stem: "判断氧化还原反应",
                  options: ["甲", "乙"],
                  answer: "A",
                  explanation: "化合价发生变化",
                  score: 100,
                  minutes: 35,
                  difficulty: "基础",
                  source_ids: [],
                  origin: "new",
                  work_lines: 0,
                },
              ],
              written: [],
              optional: [],
              source_gaps: [],
              conflicts: [],
            },
    report: {
      draft: false,
      source_issues: [],
      review_required: [],
      page_count: 2,
      conflicts: [],
      visual_review: "请复核",
      validation: { passed: true, warnings: [] },
      statistics: { content_tables: 0, note_rows: 25 },
    },
  });
  const job = {
    id: "job",
    session_id: "detail",
    kind: "generation",
    status,
    created_at: new Date().toISOString(),
    error: status === "failed" ? "模拟生成错误" : null,
    stages: [
      { index: 0, label: "教师要求已保存", status: "completed" },
      {
        index: 1,
        label: "生成教学内容",
        status: status === "completed" ? "completed" : "running",
      },
    ],
    version_id: withVersions ? "v2" : null,
  };
  return {
    id: "detail",
    settings: agent.settings(),
    messages: [{ role: "user", content: "设计本课内容" }],
    resources: [],
    sources: [],
    versions: withVersions ? [makeVersion("v1"), makeVersion("v2")] : [],
    jobs: [job],
  };
}
async function show(
  agent: (typeof agents)[number],
  status = "failed",
  withVersions = false,
) {
  window.history.replaceState(null, "", "#" + agent.id);
  localStorage.setItem(agent.key, "detail");
  const session = fixture(agent, status, withVersions);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith("/health")
        ? Response.json({ ready: true, missing: [] })
        : Response.json(session),
    ),
  );
  render(<App />);
  await screen.findByRole("button", { name: "返回备课" });
  await act(async () => {});
}

test.each(agents)(
  "$product details use the guide header, staged failure and retry interaction",
  async (agent) => {
    await show(agent);
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: new RegExp(agent.product),
      }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "启鸣 教学工作台" }),
    ).toBeNull();
    expect(screen.getByText("对话式生成")).toBeTruthy();
    const progress = screen.getByRole("status");
    expect(within(progress).getByText("生成未完成")).toBeTruthy();
    expect(within(progress).getByText("未完成")).toBeTruthy();
    expect(within(progress).getByRole("button", { name: "重试" })).toBeTruthy();
    expect(
      within(progress).getByRole("button", { name: "查看资料" }),
    ).toBeTruthy();
  },
);

test.each(agents.slice(1))(
  "$product preserves versioned previews and downloads in the shared conversation",
  async (agent) => {
    await show(agent, "completed", true);
    const label = agent.id === "courseware" ? "课件版本" : "限时练习版本";
    fireEvent.change(screen.getByRole("combobox", { name: label }), {
      target: { value: "v1" },
    });
    expect(
      screen.getByText("历史版本仅供查看，切换最新版本后可继续修改"),
    ).toBeTruthy();
    if (agent.id === "courseware") {
      expect(
        screen.getByRole("link", { name: "下载 PPTX" }).getAttribute("href"),
      ).toContain("/versions/v1/");
      fireEvent.click(screen.getByRole("button", { name: "下一页" }));
      expect(screen.getByRole("heading", { name: "课堂讨论" })).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "演示" }));
      expect(screen.getByRole("dialog", { name: "课件演示" })).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "退出演示" }));
    } else {
      expect(
        screen.getByRole("link", { name: "答案解析卷" }).getAttribute("href"),
      ).toContain("/versions/v1/");
      fireEvent.click(screen.getByRole("button", { name: "答案与解析" }));
      expect(screen.getByText("化合价发生变化")).toBeTruthy();
    }
  },
);

test.each(agents.slice(1))(
  "$product can leave its busy details without losing the active session",
  async (agent) => {
    await show(agent, "running");
    fireEvent.click(screen.getByRole("button", { name: "返回备课" }));
    expect(screen.getByRole("tab", { name: "导学案" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看任务" })).toBeTruthy();
    expect(localStorage.getItem(agent.key)).toBe("detail");
    fireEvent.click(screen.getByRole("button", { name: "查看任务" }));
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: new RegExp(agent.product),
      }),
    ).toBeTruthy();
  },
);

test.each(agents)(
  "$product completed details return to a fresh entry without rebinding the finished session",
  async (agent) => {
    await show(agent, "completed", true);
    fireEvent.click(screen.getByRole("button", { name: "返回备课" }));
    expect(localStorage.getItem(agent.key)).toBeNull();
    const label =
      agent.id === "guide"
        ? "备课要求"
        : agent.id === "courseware"
          ? "课件要求"
          : "限时练习要求";
    expect(
      (screen.getByRole("textbox", { name: label }) as HTMLTextAreaElement)
        .value,
    ).toBe("");
    expect(screen.queryByRole("button", { name: "查看任务" })).toBeNull();
  },
);

test("courseware result source button opens its cited sources directly", async () => {
  await show(agents[1], "completed", true);
  fireEvent.click(screen.getByRole("button", { name: "查看来源" }));
  const dialog = screen.getByRole("dialog", { name: "当前版本 · 来源快照" });
  expect(within(dialog).queryByRole("button", { name: "选择文件" })).toBeNull();
  expect(within(dialog).getByText("本次命中片段")).toBeTruthy();
});

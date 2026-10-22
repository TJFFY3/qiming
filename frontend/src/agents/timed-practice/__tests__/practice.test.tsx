// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import OptimizeDialog from "../components/OptimizeDialog";
import PracticeApp from "../pages/PracticeApp";
import { defaultOptions } from "../domain/types";
import { applyOptimization } from "../domain/prompt";
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

test("practice optimization includes image options, exclusive focus, cancel, reset and custom validation", () => {
  const apply = vi.fn(),
    close = vi.fn();
  render(
    <OptimizeDialog
      chapter="第三节 氧化还原反应"
      value={defaultOptions()}
      onApply={apply}
      onClose={close}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "20 分钟" }));
  fireEvent.click(screen.getByRole("button", { name: "50 分" }));
  fireEvent.click(screen.getByRole("button", { name: "计算" }));
  const group = screen.getByRole("group", { name: /重点练什么/ });
  expect(
    within(group)
      .getByRole("button", { name: "按本课安排（默认）" })
      .getAttribute("aria-pressed"),
  ).toBe("false");
  fireEvent.click(screen.getByRole("button", { name: "计算" }));
  expect(
    within(group)
      .getByRole("button", { name: "按本课安排（默认）" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(apply.mock.calls[0][0]).toMatchObject({
    duration: "20 分钟",
    score: "50 分",
  });
  fireEvent.click(
    within(screen.getByRole("group", { name: "题型和数量" })).getByRole(
      "button",
      { name: "自己指定" },
    ),
  );
  expect(
    (screen.getByRole("button", { name: "填入" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.change(screen.getByRole("textbox", { name: "题型和数量自定义" }), {
    target: { value: "5道选择题和2道解答题" },
  });
  expect(
    (screen.getByRole("button", { name: "填入" }) as HTMLButtonElement)
      .disabled,
  ).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "清除全部设置" }));
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(apply.mock.calls.at(-1)?.[0]).toEqual(defaultOptions());
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(close).toHaveBeenCalled();
});

test("reapplying optimization replaces its own section without erasing teacher prose", () => {
  const first = applyOptimization("请增加分层练习。", {
    ...defaultOptions(),
    duration: "20 分钟",
  });
  const second = applyOptimization(first, {
    ...defaultOptions(),
    score: "50 分",
  });
  expect(second).toContain("请增加分层练习。");
  expect(second).not.toContain("20 分钟");
  expect(second.match(/【限时练习优化设置】/g)?.length).toBe(1);
  expect(second).toContain("满分：50 分");
});

test("practice only uses its own namespace and does not restore guide session", async () => {
  localStorage.setItem("qiming-session", "guide-session");
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      calls.push(path);
      if (path.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (path.endsWith("/sessions") && init?.method === "POST")
        return Response.json({
          id: "practice-session",
          settings: JSON.parse(String(init.body)),
          versions: [],
          messages: [],
          jobs: [],
          resources: [],
          sources: [],
        });
      if (path.endsWith("/generate"))
        return Response.json({
          id: "j",
          status: "failed",
          kind: "generation",
          error: "test",
          stages: [],
        });
      return Response.json({
        id: "practice-session",
        versions: [],
        messages: [],
        jobs: [],
        resources: [],
        sources: [],
      });
    }),
  );
  render(<PracticeApp onAgentChange={() => {}} />);
  await act(async () => {});
  fireEvent.change(screen.getByRole("textbox", { name: "限时练习要求" }), {
    target: { value: "15分钟，5道选择题和2道解答题" },
  });
  fireEvent.click(screen.getByRole("button", { name: "生成限时练习" }));
  await waitFor(() =>
    expect(calls).toContain(
      "/api/timed-practice/sessions/practice-session/generate",
    ),
  );
  expect(calls.every((p) => p.startsWith("/api/timed-practice/"))).toBe(true);
  expect(localStorage.getItem("qiming-session")).toBe("guide-session");
  expect(localStorage.getItem("qiming-practice-session")).toBe(
    "practice-session",
  );
});

test("all agents keep independent drafts across tab switches", async () => {
  const { default: App } = await import("../../../App");
  window.history.replaceState(null, "", "#guide");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ ready: true, missing: [] })),
  );
  render(<App />);
  await act(async () => {});
  fireEvent.change(screen.getByRole("textbox", { name: "备课要求" }), {
    target: { value: "导学案独立草稿" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "限时练习" }));
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "限时练习要求" })).toBeTruthy(),
  );
  fireEvent.change(screen.getByRole("textbox", { name: "限时练习要求" }), {
    target: { value: "限时练独立草稿" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "导学案" }));
  expect(
    (screen.getByRole("textbox", { name: "备课要求" }) as HTMLTextAreaElement)
      .value,
  ).toBe("导学案独立草稿");
  fireEvent.click(screen.getByRole("tab", { name: "限时练习" }));
  expect(
    (
      screen.getByRole("textbox", {
        name: "限时练习要求",
      }) as HTMLTextAreaElement
    ).value,
  ).toBe("限时练独立草稿");
  window.history.replaceState(null, "", "#guide");
});

test("custom focus stays exclusive with default when last named focus is removed", () => {
  render(
    <OptimizeDialog
      chapter="氧化还原反应"
      value={defaultOptions()}
      onApply={() => {}}
      onClose={() => {}}
    />,
  );
  const focus = screen.getByRole("group", { name: /重点练什么/ });
  fireEvent.click(within(focus).getByRole("button", { name: "自己填写" }));
  fireEvent.change(screen.getByRole("textbox", { name: "重点自定义" }), {
    target: { value: "电子转移" },
  });
  fireEvent.click(within(focus).getByRole("button", { name: "计算" }));
  fireEvent.click(within(focus).getByRole("button", { name: "计算" }));
  expect(
    within(focus)
      .getByRole("button", { name: "按本课安排（默认）" })
      .getAttribute("aria-pressed"),
  ).toBe("false");
});

test("student preview separates answers and both downloads stay in practice namespace", async () => {
  const { default: Preview } = await import("../components/Preview");
  const version = {
    id: "v1",
    number: "v001",
    parent_id: null,
    created_at: new Date().toISOString(),
    sources: [],
    report: {
      draft: true,
      source_issues: [],
      review_required: [],
      validation: { passed: true },
    },
    content: {
      title: "预览验收",
      duration: 20,
      total_score: 50,
      source_gaps: [],
      conflicts: [],
      choice: [
        {
          stem: "判断反应类型",
          options: ["甲", "乙", "丙", "丁"],
          answer: "A",
          explanation: "答案卷专用解析",
          score: 50,
          minutes: 2,
          difficulty: "基础",
          source_ids: [],
          origin: "new" as const,
          work_lines: 2,
        },
      ],
      written: [],
      optional: [],
    },
  };
  render(
    <Preview version={version} sessionId="practice" onSources={() => {}} />,
  );
  expect(screen.queryByText(/待核验/)).toBeNull();
  expect(screen.queryByText("答案卷专用解析")).toBeNull();
  for (const name of ["学生卷", "答案解析卷"])
    expect(screen.getByRole("link", { name }).getAttribute("href")).toMatch(
      /^\/api\/timed-practice\/sessions\/practice\/versions\/v1\/files\//,
    );
  fireEvent.click(screen.getByRole("button", { name: "答案与解析" }));
  expect(screen.getByText("答案卷专用解析")).toBeTruthy();
});

test("practice resources present evidence without verification controls", async () => {
  const { default: Resources } = await import("../components/Resources");
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      Response.json({ documents: [], chunk_count: 0, synced_at: null }),
    ),
  );
  render(
    <Resources
      resources={[
        {
          id: "s",
          title: "教材",
          category: "textbook",
          locator: "第1页",
          evidence: "原始摘录",
          verified: false,
        },
      ]}
      sources={[]}
      snapshot={false}
      busy={false}
      onClose={() => {}}
      onUpload={async () => {}}
      onDelete={async () => {}}
    />,
  );
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: /教材.*第1页/ }));
  expect(screen.getByText("原始摘录")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /核对/ })).toBeNull();
  expect(screen.queryByText(/尚未核对|待核验/)).toBeNull();
});

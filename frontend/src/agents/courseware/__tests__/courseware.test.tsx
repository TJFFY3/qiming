// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "../../../App";
import OptimizeDialog from "../components/OptimizeDialog";
import { defaultOptions } from "../domain/types";
import { applyOptimization } from "../domain/prompt";

afterEach(() => {
  cleanup();
  localStorage.clear();
  window.location.hash = "";
  vi.restoreAllMocks();
});

test("courseware options fill pages, duration and focus without duplicating prompt segments", () => {
  const options = {
    ...defaultOptions(),
    pages: "15 页",
    duration: "45 分钟",
    focus: ["概念理解", "计算"],
  };
  const once = applyOptimization("安排三个互动环节", options);
  const twice = applyOptimization(once, { ...options, pages: "20 页" });
  expect(twice).toContain("安排三个互动环节");
  expect(twice).toContain("课件页数：20 页");
  expect(twice).not.toContain("15 页");
  expect(twice.match(/【课件优化提示】/g)).toHaveLength(1);
});

test("dialog cancels without changing applied options and preserves custom values on reopen", () => {
  const value = defaultOptions();
  const apply = vi.fn();
  const close = vi.fn();
  const view = render(
    <OptimizeDialog
      chapter="氧化还原反应"
      value={value}
      onApply={apply}
      onClose={close}
    />,
  );
  const pages = screen.getByRole("group", { name: "课件页数" });
  fireEvent.click(within(pages).getByRole("button", { name: "自己填写" }));
  fireEvent.change(screen.getByLabelText("课件页数自定义"), {
    target: { value: "12 页" },
  });
  fireEvent.click(screen.getByRole("button", { name: "概念理解" }));
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(apply.mock.calls[0][0]).toMatchObject({
    pages: "12 页",
    focus: ["概念理解"],
  });
  expect(value.pages).toBe("按本课安排（默认）");
  view.unmount();
  render(
    <OptimizeDialog
      chapter="氧化还原反应"
      value={apply.mock.calls[0][0]}
      onApply={apply}
      onClose={close}
    />,
  );
  expect(
    (screen.getByLabelText("课件页数自定义") as HTMLInputElement).value,
  ).toBe("12 页");
  fireEvent.click(screen.getByRole("button", { name: "清除全部设置" }));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  expect(apply).toHaveBeenCalledTimes(1);
});

test("switching agents preserves separate drafts and submits only to the courseware namespace", async () => {
  const requests: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const body =
        typeof init?.body === "string" ? JSON.parse(init.body) : null;
      requests.push({ url, body });
      if (url.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (url === "/api/courseware/sessions" && init?.method === "POST")
        return Response.json({
          id: "cw",
          settings: body,
          resources: [],
          sources: [],
          messages: [],
          versions: [],
          jobs: [],
        });
      if (url.endsWith("/generate"))
        return Response.json({
          id: "job",
          session_id: "cw",
          kind: "generation",
          status: "queued",
          stages: [],
          error: null,
          version_id: null,
        });
      if (url === "/api/courseware/sessions/cw")
        return Response.json({
          id: "cw",
          settings: body || {},
          resources: [],
          sources: [],
          messages: [],
          versions: [],
          jobs: [],
        });
      throw new Error("Unexpected " + url);
    }),
  );
  render(<App />);
  fireEvent.change(screen.getByLabelText("备课要求"), {
    target: { value: "导学案草稿" },
  });
  fireEvent.click(screen.getByRole("tab", { name: "互动课件" }));
  fireEvent.change(screen.getByLabelText("课件要求"), {
    target: { value: "设计 15 页互动课件" },
  });
  fireEvent.click(
    screen
      .getAllByRole("tab", { name: "导学案" })
      .find((e) => e.getAttribute("aria-selected") === "false")!,
  );
  expect((screen.getByLabelText("备课要求") as HTMLTextAreaElement).value).toBe(
    "导学案草稿",
  );
  fireEvent.click(screen.getByRole("tab", { name: "互动课件" }));
  expect((screen.getByLabelText("课件要求") as HTMLTextAreaElement).value).toBe(
    "设计 15 页互动课件",
  );
  expect(
    screen.queryByRole("checkbox", { name: "以待核验草案生成" }),
  ).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "生成互动课件" }));
  await waitFor(() =>
    expect(
      requests.some((r) => r.url === "/api/courseware/sessions/cw/generate"),
    ).toBe(true),
  );
  expect(requests.filter((r) => r.url === "/api/sessions")).toHaveLength(0);
  expect(localStorage.getItem("qiming-session")).toBeNull();
  expect(localStorage.getItem("qiming-courseware-session")).toBe("cw");
});

test("refresh keeps unsent courseware settings alongside its prompt after a session exists", async () => {
  window.location.hash = "#courseware";
  localStorage.setItem("qiming-courseware-session", "cw");
  const settings = {
    chapter: "第三节 氧化还原反应",
    period: "第二课时",
    edition: "人教版 必修第一册",
    grade: "高一",
    format: "传统 PPT",
    options: { ...defaultOptions(), pages: "15 页" },
  };
  localStorage.setItem(
    "qiming-courseware-draft",
    JSON.stringify({
      settings,
      prompt: "新的15页要求",
      allowDraft: true,
      sessionId: "cw",
    }),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) =>
      String(input).endsWith("/health")
        ? Response.json({ ready: true, missing: [] })
        : Response.json({
            id: "cw",
            settings: {
              ...settings,
              period: "第一课时",
              options: defaultOptions(),
            },
            resources: [],
            sources: [],
            messages: [],
            versions: [],
            jobs: [],
          }),
    ),
  );
  render(<App />);
  await waitFor(() =>
    expect((screen.getByLabelText("课件课时") as HTMLSelectElement).value).toBe(
      "第二课时",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
  const pages = screen.getByRole("group", { name: "课件页数" });
  expect(
    within(pages)
      .getByRole("button", { name: "15 页" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

test("a temporary restore failure retains the courseware session identity", async () => {
  window.location.hash = "#courseware";
  localStorage.setItem("qiming-courseware-session", "existing");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      if (String(input).endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      throw new Error("temporary network failure");
    }),
  );
  render(<App />);
  await screen.findByRole("alert");
  expect(localStorage.getItem("qiming-courseware-session")).toBe("existing");
});

test("custom focus replaces the default focus immediately in the dialog", () => {
  render(
    <OptimizeDialog
      chapter="氧化还原反应"
      value={defaultOptions()}
      onApply={() => {}}
      onClose={() => {}}
    />,
  );
  const focus = screen.getByRole("group", { name: "本课重点 （可多选）" });
  fireEvent.click(within(focus).getByRole("button", { name: "自己填写" }));
  expect(
    within(focus)
      .getByRole("button", { name: "按本课安排（默认）" })
      .getAttribute("aria-pressed"),
  ).toBe("false");
  fireEvent.click(within(focus).getByRole("button", { name: "自己填写" }));
  expect(
    within(focus)
      .getByRole("button", { name: "按本课安排（默认）" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import { defaultSettings } from "./api";

afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.restoreAllMocks();
});

test("terminal job refreshes session even when the session response is delayed", async () => {
  localStorage.setItem("qiming-session", "session");
  const job = {
    id: "job",
    session_id: "session",
    status: "running",
    stages: [],
    error: null,
    version_id: null,
    created_at: new Date().toISOString(),
  };
  const session = {
    id: "session",
    settings: defaultSettings(),
    messages: [{ role: "user", content: "设计导学案" }],
    resources: [],
    sources: [],
    versions: [],
    jobs: [job],
  };
  let sessionReads = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (url.endsWith("/jobs/job"))
        return Response.json({
          ...job,
          status: "completed",
          version_id: "v1",
          stages: [{ index: 0, label: "完成", status: "completed" }],
        });
      if (url.endsWith("/sessions/session")) {
        sessionReads++;
        if (sessionReads === 1) return Response.json(session);
        await new Promise((resolve) => setTimeout(resolve, 60));
        return Response.json({
          ...session,
          versions: [
            {
              id: "v1",
              number: "v001",
              parent_id: null,
              change_kind: "首次生成",
              content: {
                title: "回归测试导学案",
                goals: ["能够判断"],
                sections: [],
              },
              report: {
                draft: true,
                statistics: { content_tables: 0 },
                validation: { passed: true },
              },
            },
          ],
          jobs: [{ ...job, status: "completed", version_id: "v1" }],
        });
      }
      throw new Error("Unexpected URL " + url);
    }),
  );
  render(<App />);
  await waitFor(
    () =>
      expect(
        screen.getByRole("heading", { name: /回归测试导学案/ }),
      ).toBeTruthy(),
    { timeout: 3000 },
  );
  expect(screen.getByRole("link", { name: "下载 Word" })).toBeTruthy();
});

test("optimization cancel preserves last applied options", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ ready: false, missing: [] })),
  );
  render(<App />);
  await act(async () => {});
  fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
  fireEvent.click(screen.getByRole("button", { name: "15 分钟" }));
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(
    (screen.getByRole("textbox", { name: "备课要求" }) as HTMLTextAreaElement)
      .value,
  ).toContain("自学用时：15 分钟");
  fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
  fireEvent.click(screen.getByRole("button", { name: "20 分钟" }));
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
  expect(
    screen
      .getByRole("button", { name: "15 分钟" })
      .getAttribute("aria-pressed"),
  ).toBe("true");
});

test("retry of a failed regeneration remains generation when an earlier version exists", async () => {
  localStorage.setItem("qiming-session", "session");
  const job = {
    id: "failed-job",
    session_id: "session",
    kind: "generation",
    status: "failed",
    stages: [],
    error: "模拟检索失败",
    version_id: null,
    created_at: new Date().toISOString(),
  };
  const version = {
    id: "v1",
    number: "v001",
    parent_id: null,
    change_kind: "首次生成",
    content: { title: "旧版", goals: ["目标"], sections: [] },
    sources: [],
    report: {
      draft: true,
      source_issues: [],
      statistics: { content_tables: 0 },
      validation: { passed: true },
    },
  };
  const session = {
    id: "session",
    settings: defaultSettings(),
    messages: [{ role: "user", content: "重新生成" }],
    resources: [],
    sources: [],
    versions: [version],
    jobs: [job],
  };
  const calls: string[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push((init?.method || "GET") + " " + url);
      if (url.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (url.endsWith("/generate") || url.endsWith("/revise"))
        return Response.json(job);
      return Response.json(session);
    }),
  );
  render(<App />);
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "重试" })).toBeTruthy(),
  );
  fireEvent.click(screen.getByRole("button", { name: "重试" }));
  await waitFor(() =>
    expect(calls).toContain("POST /api/sessions/session/generate"),
  );
  expect(calls).not.toContain("POST /api/sessions/session/revise");
});

test("generation does not require a source-verification opt-in", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json({ ready: true, missing: [] })),
  );
  render(<App />);
  await act(async () => {});
  expect(
    screen.queryByRole("checkbox", { name: /允许生成待核验草案/ }),
  ).toBeNull();
});

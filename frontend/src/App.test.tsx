// @vitest-environment jsdom
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "./App";
import { defaultSettings } from "./agents/study-guide/services/api";

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

test.each(["新建备课", "返回备课"])(
  "%s starts a fresh conversation with default optimization and no old prompt",
  async (entry) => {
    localStorage.setItem("qiming-session", "old-session");
    const settings = defaultSettings();
    settings.options.scope = "自定义学习范围";
    settings.options.duration = "15 分钟";
    settings.options.tasks = "5个任务";
    settings.options.difficulty = "综合提高";
    settings.options.hints = "详细提示";
    settings.options.focus = ["计算"];
    settings.options.extra = "上次会话的补充要求";
    const session = {
      id: "old-session",
      settings,
      messages: [],
      resources: [],
      sources: [],
      versions: [],
      jobs: [
        {
          id: "old-job",
          session_id: "old-session",
          kind: "generation",
          status: "failed",
          stages: [],
          error: "旧任务",
          version_id: null,
          created_at: new Date().toISOString(),
        },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        String(input).endsWith("/health")
          ? Response.json({ ready: true, missing: [] })
          : Response.json(session),
      ),
    );
    render(<App />);
    await screen.findByRole("button", { name: entry });
    fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
    fireEvent.click(screen.getByRole("button", { name: "填入" }));
    expect(
      (
        screen.getByRole("textbox", {
          name: "继续修改导学案",
        }) as HTMLTextAreaElement
      ).value,
    ).toContain("15 分钟");
    fireEvent.click(screen.getByRole("button", { name: entry }));
    expect(localStorage.getItem("qiming-session")).toBeNull();
    expect(
      (screen.getByRole("textbox", { name: "备课要求" }) as HTMLTextAreaElement)
        .value,
    ).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "优化提示" }));
    expect(
      screen
        .getByRole("button", { name: "15 分钟" })
        .getAttribute("aria-pressed"),
    ).toBe("false");
    expect(
      (screen.getByRole("textbox", { name: /补充要求/ }) as HTMLTextAreaElement)
        .value,
    ).toBe("");
    for (const label of [
      "学习范围",
      "自学用时",
      "任务数量",
      "内容难度",
      "提示写多细",
    ]) {
      const name =
        label === "学习范围" ? "当前课时（默认）" : "按本课安排（默认）";
      expect(
        within(screen.getByRole("group", { name: label }))
          .getByRole("button", { name })
          .getAttribute("aria-pressed"),
      ).toBe("true");
    }
    expect(
      within(screen.getByRole("group", { name: /本课重点/ }))
        .getByRole("button", { name: "按本课安排（默认）" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(settings.options.duration).toBe("15 分钟");
  },
);

test.each(["queued", "running"])(
  "%s guide task can return home and switch agents while preserving progress",
  async (status) => {
    window.history.replaceState(null, "", "#guide");
    localStorage.setItem("qiming-session", "active-guide");
    let completed = false;
    const job = {
      id: "active-job",
      session_id: "active-guide",
      kind: "generation",
      status,
      stages: [],
      error: null,
      version_id: null,
      created_at: new Date().toISOString(),
    };
    const version = {
      id: "done",
      number: "v001",
      parent_id: null,
      change_kind: "首次生成",
      created_at: "",
      content_sha256: "hash",
      sources: [],
      content: {
        title: "后台完成的导学案",
        goals: ["能够判断氧化还原反应"],
        sections: [],
      },
      report: {
        draft: false,
        source_issues: [],
        statistics: { content_tables: 0, note_rows: 25 },
        validation: { passed: true },
      },
    };
    const requests: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        requests.push((init?.method || "GET") + " " + url);
        if (url.endsWith("/health"))
          return Response.json({ ready: true, missing: [] });
        const current = completed
          ? { ...job, status: "completed", version_id: "done" }
          : job;
        if (url === "/api/jobs/active-job") return Response.json(current);
        if (url === "/api/sessions/active-guide")
          return Response.json({
            id: "active-guide",
            settings: defaultSettings(),
            messages: [{ role: "user", content: "生成导学案" }],
            resources: [],
            sources: [],
            versions: completed ? [version] : [],
            jobs: [current],
          });
        throw new Error("Unexpected " + url);
      }),
    );
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "返回备课" }));
    expect(screen.getByRole("tab", { name: "互动课件" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "查看任务" })).toBeTruthy();
    expect(localStorage.getItem("qiming-session")).toBe("active-guide");
    fireEvent.click(screen.getByRole("tab", { name: "互动课件" }));
    await screen.findByRole("textbox", { name: "课件要求" });
    fireEvent.click(screen.getByRole("tab", { name: "限时练习" }));
    await screen.findByRole("textbox", { name: "限时练习要求" });
    completed = true;
    await waitFor(
      () =>
        expect(
          requests.filter((r) => r === "GET /api/sessions/active-guide").length,
        ).toBeGreaterThan(1),
      { timeout: 3000 },
    );
    expect(screen.getByRole("textbox", { name: "限时练习要求" })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "导学案" }));
    fireEvent.click(screen.getByRole("button", { name: "查看任务" }));
    expect(
      screen.getByRole("heading", { name: "后台完成的导学案" }),
    ).toBeTruthy();
    expect(requests.every((r) => r.startsWith("GET "))).toBe(true);
  },
);

test("returning home while submission is pending is not undone by its delayed response", async () => {
  window.history.replaceState(null, "", "#guide");
  localStorage.setItem("qiming-session", "pending-guide");
  const failed = {
    id: "old",
    session_id: "pending-guide",
    kind: "generation",
    status: "failed",
    stages: [],
    error: "上次失败",
    version_id: null,
    created_at: new Date().toISOString(),
  };
  const job = { ...failed, id: "new", status: "running", error: null };
  const session = {
    id: "pending-guide",
    settings: defaultSettings(),
    messages: [],
    resources: [],
    sources: [],
    versions: [],
    jobs: [failed],
  };
  let accepted = false,
    started = false;
  let release: (value: Response) => void = () => {};
  const response = new Promise<Response>((resolve) => {
    release = resolve;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (url.endsWith("/generate") && init?.method === "POST") {
        started = true;
        return response;
      }
      if (url.endsWith("/jobs/new")) return Response.json(job);
      return Response.json({ ...session, jobs: accepted ? [job] : [failed] });
    }),
  );
  render(<App />);
  const prompt = await screen.findByRole("textbox", { name: "继续修改导学案" });
  fireEvent.change(prompt, { target: { value: "重新生成导学案" } });
  fireEvent.click(screen.getByRole("button", { name: "提交修改" }));
  await waitFor(() => expect(started).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: "返回备课" }));
  await act(async () => {
    accepted = true;
    release(Response.json(job));
  });
  expect(screen.getByRole("tab", { name: "互动课件" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看任务" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "返回备课" })).toBeNull();
  expect(localStorage.getItem("qiming-session")).toBe("pending-guide");
});

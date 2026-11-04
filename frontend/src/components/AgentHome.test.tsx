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
import App from "../App";
afterEach(() => {
  cleanup();
  localStorage.clear();
  window.history.replaceState(null, "", "#guide");
  vi.restoreAllMocks();
});

test("all entry pages offer the same native chapter and two-period interaction", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input) => String(input).includes("/library/chapters") ? Response.json({chapters:["第一章 知识库章节", "第二章 知识库章节"]}) : Response.json({ ready: true, missing: [] })),
  );
  render(<App />);
  await act(async () => {});
  for (const agent of [
    { name: "导学案", chapter: "章节 / 知识点", period: "课时" },
    { name: "互动课件", chapter: "课件章节", period: "课件课时" },
    { name: "限时练习", chapter: "限时练习章节", period: "限时练习课时" },
  ]) {
    fireEvent.click(screen.getByRole("tab", { name: agent.name }));
    await act(async () => {});
    const chapter = screen.getByRole("combobox", { name: agent.chapter });
    expect(chapter.tagName).toBe("SELECT");
    await screen.findByRole("option", {name:"第二章 知识库章节"});
    expect(within(chapter).queryByRole("option",{name:"第三节 氧化还原反应"})).toBeNull();
    fireEvent.change(chapter, { target: { value: "第二章 知识库章节" } });
    expect((chapter as HTMLSelectElement).value).toBe("第二章 知识库章节");
    const period = screen.getByRole("combobox", { name: agent.period });
    expect(
      within(period)
        .getAllByRole("option")
        .map((n) => n.textContent),
    ).toEqual(["第一课时", "第二课时"]);
    expect(
      screen.getByRole("heading", { name: /Fast AI\s*，帮你备课/ }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "资料库" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "上传附件" })).toBeTruthy();
    const subjectLabel = agent.name === "导学案" ? "学科" : agent.name === "互动课件" ? "课件学科" : "限时练习学科";
    for (const field of [subjectLabel, agent.name === "导学案" ? "年级" : agent.name === "互动课件" ? "课件年级" : "限时练习年级"]) {
      expect(screen.getByLabelText(field).closest(".composer")).toBeTruthy();
    }
    expect(screen.queryByRole("textbox",{name:/教材版本/})).toBeNull();
    expect(screen.getByLabelText(subjectLabel).closest(".composer-lesson-fields")?.querySelector("select")?.getAttribute("aria-label")).toBe(agent.name === "导学案" ? "年级" : agent.name === "互动课件" ? "课件年级" : "限时练习年级");
    expect(document.querySelector(".resource-toolbar")).toBeNull();
    expect(screen.queryByRole("combobox", { name: "课件格式" })).toBeNull();
    expect(screen.queryByText("教学工作台")).toBeNull();
    expect(screen.queryByText("从本课内容开始，准备一份新的教学文件")).toBeNull();
  }
});

test("practice Enter keeps composing and Ctrl+Enter submits once with the selected lesson", async () => {
  window.history.replaceState(null, "", "#practice");
  const submitted: { url: string; body: any }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input),
        body = init?.body ? JSON.parse(String(init.body)) : null;
      if (init?.method === "POST") submitted.push({ url, body });
      if (url.endsWith("/health"))
        return Response.json({ ready: true, missing: [] });
      if (url.endsWith("/generate"))
        return Response.json({
          id: "job",
          session_id: "practice",
          kind: "generation",
          status: "failed",
          stages: [],
          error: "测试终止",
        });
      return Response.json({
        id: "practice",
        settings: body,
        versions: [],
        messages: [],
        jobs: [],
        sources: [],
        resources: [],
      });
    }),
  );
  render(<App />);
  await act(async () => {});
  const prompt = screen.getByRole("textbox", { name: "限时练习要求" });
  fireEvent.change(prompt, { target: { value: "设置分层练习" } });
  fireEvent.change(screen.getByRole("combobox", { name: "限时练习课时" }), {
    target: { value: "第二课时" },
  });
  fireEvent.keyDown(prompt, { key: "Enter" });
  await act(async () => {});
  expect(submitted).toHaveLength(0);
  fireEvent.keyDown(prompt, { key: "Enter", ctrlKey: true });
  await waitFor(() =>
    expect(submitted.some((r) => r.url.endsWith("/generate"))).toBe(true),
  );
  expect(submitted.find((r) => r.url.endsWith("/sessions"))?.body.period).toBe(
    "第二课时",
  );
  expect(submitted.filter((r) => r.url.endsWith("/generate"))).toHaveLength(1);
});

test.each([
  { id: "guide", product: "导学案", submit: "生成导学案" },
  { id: "courseware", product: "互动课件", submit: "生成互动课件" },
  { id: "practice", product: "限时练习", submit: "生成限时练习" },
])(
  "$product default generation sends the complete lesson prompt",
  async (agent) => {
    window.history.replaceState(null, "", "#" + agent.id);
    let submitted = "";
    let settings: unknown;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        const body = init?.body ? JSON.parse(String(init.body)) : null;
        if (url.endsWith("/health"))
          return Response.json({ ready: true, missing: [] });
        if (init?.method === "POST" && url.endsWith("/sessions"))
          settings = body;
        if (url.endsWith("/generate")) {
          submitted = body.prompt;
          return Response.json({
            id: "job",
            session_id: "lesson",
            kind: "generation",
            status: "failed",
            stages: [],
            error: "测试结束",
          });
        }
        return Response.json({
          id: "lesson",
          settings,
          versions: [],
          messages: [],
          jobs: [],
          resources: [],
          sources: [],
        });
      }),
    );
    render(<App />);
    await act(async () => {});
    fireEvent.click(screen.getByRole("button", { name: agent.submit }));
    await waitFor(() =>
      expect(submitted).toContain(
        `请根据本课内容生成一份${agent.product}。\n\n学科：化学\n教材版本：人教版 必修第一册\n年级：高一\n章节 / 知识点：第三节 氧化还原反应\n课时：第一课时`,
      ),
    );
  },
);

test.each(["guide", "courseware", "practice"])("%s prevents new sessions while an attachment is uploading", async (agent) => {
  window.history.replaceState(null, "", "#" + agent);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let session: any;
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/health")) return Response.json({ready:true,missing:[]});
    if (url.endsWith("/resources") && init?.method === "POST") {
      await pending;
      return Response.json({});
    }
    if (url.endsWith("/sessions") && init?.method === "POST") {
      session = { id:"attachment-session", settings:JSON.parse(String(init.body)), messages:[], resources:[], sources:[], versions:[], jobs:[] };
    }
    return Response.json(session || {});
  }));
  render(<App />);
  await act(async () => {});
  const subjectLabel = agent === "guide" ? "学科" : agent === "courseware" ? "课件学科" : "限时练习学科";
  const subject = screen.getByRole("combobox", {name:subjectLabel});
  const order=["语文","数学","英语","物理","化学","生物","政治","历史","地理"];
  expect(within(subject).getAllByRole("option").map(item => item.textContent)).toEqual(order);
  fireEvent.change(subject, {target:{value:"数学"}});
  expect(within(subject).getAllByRole("option").map(item => item.textContent)).toEqual(order);
  fireEvent.change(screen.getByLabelText("上传附件文件"), {target:{files:[new File(["教材"], "教材.txt")]}});
  await waitFor(() => expect(screen.getByRole("button", {name:"新建任务"}).hasAttribute("disabled")).toBe(true));
  fireEvent.click(screen.getByRole("button", {name:"新建任务"}));
  await act(async () => { release(); await pending; });
  await waitFor(() => expect(screen.getByRole("button", {name:"新建任务"}).hasAttribute("disabled")).toBe(false));
  expect(session.settings.subject).toBe("数学");
  expect(session.settings.chapter).toBe("第一章 集合与常用逻辑用语");
  expect(localStorage.getItem(agent === "guide" ? "qiming-session" : agent === "courseware" ? "qiming-courseware-session" : "qiming-practice-session")).toBe("attachment-session");
});

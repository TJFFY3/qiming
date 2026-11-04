// @vitest-environment jsdom
import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import AgentWorkbench from "./AgentWorkbench";
import { ConversationHeader, ConversationView } from "./AgentConversation";
import Modal from "./Modal";

afterEach(() => { cleanup(); vi.useRealTimers(); });
const actions = () => ({ onAgentChange: vi.fn(), onResources: vi.fn(), onHistory: vi.fn(), onNew: vi.fn(), onHome: vi.fn() });

test("knowledge and history are reachable from the persistent left menu", () => {
  const callbacks = actions();
  render(<AgentWorkbench agent="guide" ready busy={false} {...callbacks}><p>任务对话</p></AgentWorkbench>);
  const menu = screen.getByRole("complementary", { name: "工作台菜单" });
  fireEvent.click(within(menu).getByRole("button", { name: "资料库" }));
  expect(callbacks.onResources).toHaveBeenCalledOnce();
  fireEvent.click(within(menu).getByRole("button", { name: "历史备课" }));
  expect(callbacks.onHistory).toHaveBeenCalledOnce();
  expect(within(menu).queryByRole("navigation", {name:"智能体导航"})).toBeNull();
});

test("progress stays in chat while versions and files live in the right preview", () => {
  render(<AgentWorkbench agent="guide" ready busy {...actions()}>
    <ConversationView request="设计氧化还原反应导学案" product="导学案" busy
      job={{id:"j",status:"running",stages:[{label:"正在装配Word",status:"running"}]}}
      onSources={vi.fn()} onRetry={vi.fn()} version={{id:"v1",number:"v001"}}
      versions={[{id:"v1",number:"v001"}]} onVersion={vi.fn()}>
      <article>导学案文件正文</article>
    </ConversationView>
  </AgentWorkbench>);
  const preview = screen.getByRole("complementary", { name: "文件预览" });
  expect(within(preview).queryByText("正在装配Word")).toBeNull();
  expect(screen.getByText("正在装配Word").closest(".workbench-main")).toBeTruthy();
  expect(within(preview).getByText("导学案文件正文")).toBeTruthy();
  expect(within(preview).getByRole("combobox", {name:"选择版本"})).toBeTruthy();
  expect(within(preview).queryByText("设计氧化还原反应导学案")).toBeNull();
  expect(screen.getByText("设计氧化还原反应导学案")).toBeTruthy();
});

test("knowledge and history panels share the right preview and do not lock the rest of the workspace", () => {
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()}>
    <Modal title="历史备课" placement="sidebar" onClose={vi.fn()}><p>氧化还原反应 · v001</p></Modal>
  </AgentWorkbench>);
  const panel = screen.getByRole("dialog", {name:"历史备课"});
  expect(panel.closest(".workbench-panel-slot")).toBeTruthy();
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-panel")).toBe("true");
  expect(panel.getAttribute("aria-modal")).not.toBe("true");
  expect(document.body.style.overflow).not.toBe("hidden");
  expect(panel.closest(".workbench-preview")).toBeTruthy();
});

test("new task is disabled while running and mobile preview can be selected", () => {
  render(<AgentWorkbench agent="practice" ready busy {...actions()}><p>对话内容</p></AgentWorkbench>);
  expect(screen.getByRole("button", {name:"新建任务"}).hasAttribute("disabled")).toBe(true);
  fireEvent.click(screen.getByRole("button", {name:"查看文件预览"}));
  expect(screen.getByRole("complementary", {name:"文件预览"}).closest(".agent-workbench")?.getAttribute("data-pane")).toBe("preview");
});

 test("all teacher revisions and assistant replies remain in the conversation", () => {
  render(<AgentWorkbench agent="courseware" ready busy={false} {...actions()}>
    <ConversationView request="补充实验" messages={[{role:"user",content:"生成课件"},{role:"assistant",content:"已生成 v001"},{role:"user",content:"补充实验"}]} product="互动课件" busy={false} onSources={vi.fn()} onRetry={vi.fn()} versions={[]} onVersion={vi.fn()} />
  </AgentWorkbench>);
  for (const text of ["生成课件", "已生成 v001", "补充实验"]) expect(screen.getByText(text).closest(".workbench-main")).toBeTruthy();
 });
 test("preview can be hidden and reopened without losing the file", () => {
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()}><p>任务对话</p></AgentWorkbench>);
  fireEvent.click(screen.getByRole("button", {name:"隐藏文件预览"}));
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-preview")).toBe("false");
  fireEvent.click(screen.getByRole("button", {name:"显示文件预览"}));
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-preview")).toBe("true");
 });
 test("new task returns to chat and closes the mobile menu", () => {
  const callbacks=actions();
  render(<AgentWorkbench agent="guide" ready busy={false} {...callbacks}><p>对话</p></AgentWorkbench>);
  fireEvent.click(screen.getByRole("button", {name:"查看文件预览"}));
  fireEvent.click(screen.getByRole("button", {name:"展开工作台菜单"}));
  fireEvent.click(screen.getByRole("button", {name:"新建任务"}));
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-pane")).toBe("chat");
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-menu")).toBe("false");
  expect(callbacks.onNew).toHaveBeenCalledOnce();
 });

test("closing the right panel allows it to reopen", () => {
  function Workspace() {
    const [open, setOpen] = useState(false);
    return <AgentWorkbench agent="guide" ready busy={false} {...actions()}>
      <button onClick={() => setOpen(true)}>上传本课资料</button>
      {open && <Modal title="本课资料" placement="sidebar" onClose={() => setOpen(false)}>文件列表</Modal>}
    </AgentWorkbench>;
  }
  render(<Workspace />);
  fireEvent.click(screen.getByRole("button", {name:"上传本课资料"}));
  expect(screen.getByRole("dialog", {name:"本课资料"})).toBeTruthy();
  fireEvent.click(screen.getByRole("button", {name:"隐藏文件预览"}));
  expect(screen.queryByRole("dialog", {name:"本课资料"})).toBeNull();
  fireEvent.click(screen.getByRole("button", {name:"上传本课资料"}));
  expect(screen.getByRole("dialog", {name:"本课资料"})).toBeTruthy();
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-panel")).toBe("true");
});

test("upload attachment is next to send and passes files through the agent callback", async () => {
  const upload = vi.fn().mockResolvedValue(undefined);
  const { default: Composer } = await import("./Composer");
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()} onUpload={upload}>
    <Composer settings={{chapter:"氧化还原反应",period:"第一课时"}} onSettings={vi.fn()} prompt="生成" onPrompt={vi.fn()} onSubmit={vi.fn()} onOptimize={vi.fn()} onHistory={vi.fn()} busy={false} />
  </AgentWorkbench>);
  expect(screen.getByRole("button", {name:"上传附件"}).parentElement).toBe(screen.getByRole("button", {name:"生成导学案"}).parentElement);
  const file = new File(["化学教材"], "教材.txt", {type:"text/plain"});
  fireEvent.change(screen.getByLabelText("上传附件文件"), {target:{files:[file]}});
  await vi.waitFor(() => expect(upload).toHaveBeenCalledWith(file, "textbook"));
  expect(screen.getByRole("button", {name:"隐藏文件预览"}).textContent).toBe("");
});

test("preview toggle stays outside agent conversation and preview columns", () => {
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()}>
    <ConversationHeader chapter="物质的分类及转化" period="第一课时" product="导学案" onBack={vi.fn()} onSources={vi.fn()} onHistory={vi.fn()} onNew={vi.fn()} />
  </AgentWorkbench>);
  const toggle=screen.getByRole("button", {name:"隐藏文件预览"});
  expect(toggle.closest(".workbench-global-controls")).toBeTruthy();
  expect(toggle.closest(".workbench-main")).toBeNull();
  expect(screen.getByRole("button", {name:"返回备课"}).textContent).toBe("");
  expect(screen.getByRole("heading",{name:/物质的分类及转化/}).closest(".workbench-shared-header")).toBeTruthy();
  expect(toggle.closest(".workbench-shared-header")).toBeTruthy();
  expect(screen.queryByText("对话式生成")).toBeNull();
  expect(screen.queryByRole("button", {name:"关闭文件预览"})).toBeNull();
  expect(screen.queryByRole("button", {name:"新建备课"})).toBeNull();
  expect(document.querySelector(".workbench-view-controls")).toBeNull();
  fireEvent.click(toggle);
  expect(screen.getByRole("button", {name:"显示文件预览"}).closest(".workbench-global-controls")).toBeTruthy();
});

test("preview divider resizes with the keyboard and retains width after hiding", () => {
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()}><p>任务</p></AgentWorkbench>);
  const divider=screen.getByRole("separator",{name:"调整预览区域宽度"});
  expect(divider.getAttribute("aria-valuenow")).toBe("55");
  fireEvent.keyDown(divider,{key:"ArrowLeft"});
  expect(divider.getAttribute("aria-valuenow")).toBe("60");
  fireEvent.click(screen.getByRole("button",{name:"隐藏文件预览"}));
  expect(screen.queryByRole("separator")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"显示文件预览"}));
  expect(screen.getByRole("separator").getAttribute("aria-valuenow")).toBe("60");
  fireEvent.doubleClick(screen.getByRole("separator"));
  expect(screen.getByRole("separator").getAttribute("aria-valuenow")).toBe("55");
});

test("back arrow returns mobile preview to the task composer", () => {
  const back=vi.fn();
  render(<AgentWorkbench agent="guide" ready busy={false} {...actions()}>
    <ConversationHeader chapter="本课" period="第一课时" product="导学案" onBack={back} onSources={vi.fn()} onHistory={vi.fn()} onNew={vi.fn()} />
  </AgentWorkbench>);
  fireEvent.click(screen.getByRole("button",{name:"查看文件预览"}));
  fireEvent.click(screen.getByRole("button",{name:"返回备课"}));
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-pane")).toBe("chat");
  expect(back).toHaveBeenCalledOnce();
});

test("finished progress shows fixed stage and total durations", () => {
  render(<ConversationView request="生成" product="导学案" busy={false} versions={[]} onVersion={vi.fn()} onSources={vi.fn()} onRetry={vi.fn()}
    job={{id:"timed",status:"completed",created_at:"2026-11-04T00:00:00Z",ended_at:"2026-11-04T00:01:15Z",duration_seconds:75,stages:[{label:"检索",status:"completed",duration_seconds:5},{label:"生成",status:"completed",duration_seconds:70}]}} />);
  expect(screen.getByText("5秒")).toBeTruthy();
  expect(screen.getByText("1分10秒")).toBeTruthy();
  expect(screen.getByText("总耗时 1分15秒")).toBeTruthy();
});

test("running stage and task timers advance together", () => {
  vi.useFakeTimers();vi.setSystemTime(new Date("2026-11-04T00:00:07Z"));
  render(<ConversationView request="生成" product="导学案" busy versions={[]} onVersion={vi.fn()} onSources={vi.fn()} onRetry={vi.fn()}
    job={{id:"running-timed",status:"running",created_at:"2026-11-04T00:00:00Z",stages:[{label:"生成",status:"running",started_at:"2026-11-04T00:00:05Z"}]}} />);
  expect(screen.getByText("2秒")).toBeTruthy();
  act(() => vi.advanceTimersByTime(4000));
  expect(screen.getByText("6秒")).toBeTruthy();
  expect(screen.getByText(/已用时 11秒/)).toBeTruthy();
});

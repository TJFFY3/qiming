// @vitest-environment jsdom
import {
  cleanup,
  act,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Composer from "./Composer";
import { useState } from "react";
import { defaultSettings } from "../agents/study-guide/services/api";
afterEach(() => {cleanup();vi.unstubAllGlobals();});

function LessonHarness({ onSubmit = vi.fn() }: { onSubmit?: (settings: ReturnType<typeof defaultSettings>) => void }) {
  // 模拟升级前保存在草稿里的固定章节。
  const [settings, setSettings] = useState({...defaultSettings(), chapter:"第三节 氧化还原反应"});
  return <Composer settings={settings} onSettings={setSettings} prompt="" onPrompt={vi.fn()} onSubmit={() => onSubmit(settings)} onOptimize={vi.fn()} onHistory={vi.fn()} busy={false} />;
}

test("unconfirmed legacy chapters are hidden and cannot be submitted while loading", async () => {
  let resolve!: (value: Response) => void;
  const pending = new Promise<Response>(done => {resolve=done;});
  vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("/library/chapters") ? pending : Response.json({subjects:["化学"]})));
  const submit = vi.fn();
  render(<LessonHarness onSubmit={submit} />);
  const chapter = screen.getByRole("combobox", {name:"章节 / 知识点"}) as HTMLSelectElement;
  expect(within(chapter).queryByRole("option", {name:"第三节 氧化还原反应"})).toBeNull();
  expect(chapter.disabled).toBe(true);
  expect((screen.getByRole("button", {name:"生成导学案"}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.keyDown(screen.getByRole("textbox", {name:"备课要求"}), {key:"Enter", ctrlKey:true});
  expect(submit).not.toHaveBeenCalled();
  await act(async () => {resolve(Response.json({chapters:["第一章 物质及其变化"]}));await pending;});
  await waitFor(() => expect(chapter.value).toBe("第一章 物质及其变化"));
  fireEvent.click(screen.getByRole("button", {name:"生成导学案"}));
  expect(submit).toHaveBeenCalledWith(expect.objectContaining({chapter:"第一章 物质及其变化"}));
});

test("failed chapter reads cannot fall back to old topics and support retry", async () => {
  let attempts=0;
  vi.stubGlobal("fetch", vi.fn(async input => {
    if (!String(input).includes("/library/chapters")) return Response.json({subjects:["化学"]});
    return ++attempts === 1 ? Response.json({detail:"目录暂不可用"}, {status:502}) : Response.json({chapters:["第一章 物质及其变化"]});
  }));
  render(<LessonHarness />);
  await screen.findByText(/目录暂不可用/);
  expect(screen.queryByRole("option", {name:"第三节 氧化还原反应"})).toBeNull();
  expect((screen.getByRole("button", {name:"生成导学案"}) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole("button", {name:"重试读取章节"}));
  await waitFor(() => expect((screen.getByRole("combobox", {name:"章节 / 知识点"}) as HTMLSelectElement).value).toBe("第一章 物质及其变化"));
});

test("empty knowledge catalogs do not retain a selectable legacy topic", async () => {
  vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("/library/chapters") ? Response.json({chapters:[]}) : Response.json({subjects:["化学"]})));
  render(<LessonHarness />);
  await screen.findByText(/该学科知识库暂无章节/);
  expect(screen.queryByRole("option", {name:"第三节 氧化还原反应"})).toBeNull();
  expect((screen.getByRole("button", {name:"生成导学案"}) as HTMLButtonElement).disabled).toBe(true);
});
test("chapter uses a native select and period offers exactly the first two lessons", async () => {
  vi.stubGlobal("fetch", vi.fn(async input => String(input).includes("/library/chapters") ? Response.json({chapters:["第一章 物质及其变化","第二章 海水中的重要元素"]}) : Response.json({subjects:["化学"]})));
  const change = vi.fn();
  render(
    <Composer
      settings={defaultSettings()}
      onSettings={change}
      prompt=""
      onPrompt={vi.fn()}
      onSubmit={vi.fn()}
      onOptimize={vi.fn()}
      onHistory={vi.fn()}
      busy={false}
    />,
  );
  expect(screen.queryAllByText("⌄")).toHaveLength(0);
  const period = screen.getByRole("combobox", { name: "课时" });
  expect(within(period).getByRole("option", { name: "第二课时" })).toBeTruthy();
  fireEvent.change(period, { target: { value: "第二课时" } });
  expect(change).toHaveBeenCalledWith(
    expect.objectContaining({ period: "第二课时" }),
  );
  const chapter = screen.getByRole("combobox", { name: "章节 / 知识点" });
  expect(
    await within(chapter).findByRole("option", { name: "第一章 物质及其变化" }),
  ).toBeTruthy();
  expect(
    within(period)
      .getAllByRole("option")
      .map((option) => option.textContent),
  ).toEqual(["第一课时", "第二课时"]);
  fireEvent.change(chapter, { target: { value: "第二章 海水中的重要元素" } });
  expect(change).toHaveBeenCalledWith(
    expect.objectContaining({ chapter: "第二章 海水中的重要元素" }),
  );
});

test("keyboard submission obeys the same empty-prompt guard and ignores IME confirmation", () => {
  const submit = vi.fn();
  const props = {
    settings: {...defaultSettings(), chapter:"氧化还原反应"},
    onSettings: vi.fn(),
    prompt: "",
    onPrompt: vi.fn(),
    onSubmit: submit,
    onOptimize: vi.fn(),
    onHistory: vi.fn(),
    busy: false,
    conversation: true,
  };
  const view = render(<Composer {...props} />);
  const input = screen.getByRole("textbox", { name: "继续修改导学案" });
  expect(
    (screen.getByRole("button", { name: "提交修改" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
  fireEvent.keyDown(input, { key: "Enter", ctrlKey: true });
  expect(submit).not.toHaveBeenCalled();
  view.rerender(<Composer {...props} prompt="增加一题" />);
  fireEvent.keyDown(input, { key: "Enter", metaKey: true, isComposing: true });
  expect(submit).not.toHaveBeenCalled();
  fireEvent.keyDown(input, { key: "Enter", metaKey: true });
  expect(submit).toHaveBeenCalledTimes(1);
});

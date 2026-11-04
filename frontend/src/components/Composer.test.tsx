// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Composer from "./Composer";
import { defaultSettings } from "../agents/study-guide/services/api";
afterEach(() => {cleanup();vi.unstubAllGlobals();});
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
    settings: defaultSettings(),
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

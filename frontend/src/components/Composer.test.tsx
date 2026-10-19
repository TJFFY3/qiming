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
import { defaultSettings } from "../api";
afterEach(cleanup);
test("chapter and period keep native suggestions without duplicate arrows", () => {
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
  expect(chapter.getAttribute("list")).toBe("chapters");
  fireEvent.change(chapter, { target: { value: "第一节 物质的分类及转化" } });
  expect(change).toHaveBeenCalledWith(
    expect.objectContaining({ chapter: "第一节 物质的分类及转化" }),
  );
});

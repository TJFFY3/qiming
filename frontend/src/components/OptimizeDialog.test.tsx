// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import OptimizeDialog from "./OptimizeDialog";
import { defaultOptions } from "../api";
afterEach(cleanup);
test("custom focus is composed exactly once on repeated apply and can be deselected", () => {
  const apply = vi.fn();
  const value = { ...defaultOptions(), focus: ["概念理解", "电子转移"] };
  const view = render(
    <OptimizeDialog
      chapter="课时"
      value={value}
      onApply={apply}
      onClose={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(apply.mock.calls[0][0].focus).toEqual(["概念理解", "电子转移"]);
  view.unmount();
  render(
    <OptimizeDialog
      chapter="课时"
      value={value}
      onApply={apply}
      onClose={() => {}}
    />,
  );
  fireEvent.click(
    screen
      .getByRole("group", { name: "本课重点 （可多选）" })
      .querySelectorAll("button")[6],
  );
  fireEvent.click(screen.getByRole("button", { name: "填入" }));
  expect(apply.mock.calls[1][0].focus).toEqual(["概念理解"]);
});

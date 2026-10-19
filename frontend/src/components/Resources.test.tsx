// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Resources from "./Resources";
afterEach(cleanup);
test("historical source snapshot displays original gaps and cannot be edited", () => {
  render(
    <Resources
      snapshot
      sourceIssues={["教材页码尚待核对"]}
      sources={[
        {
          id: "old",
          title: "旧版来源",
          category: "reference",
          locator: "切片1",
          evidence: "旧版摘录",
          verified: false,
        },
      ]}
      resources={[]}
      onUpload={vi.fn()}
      onReview={vi.fn()}
      onClose={() => {}}
      busy={false}
    />,
  );
  expect(screen.getByText("教材页码尚待核对")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "选择文件" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /旧版来源/ }));
  expect(screen.getByText("旧版摘录")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "我已核对原文" })).toBeNull();
});

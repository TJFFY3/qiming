// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import OutlinePreview from "./OutlinePreview";
import type { Version } from "../api";
afterEach(cleanup);
test("historical source verification markers are hidden while source gaps and downloads remain", () => {
  const version: Version = {
    id: "v",
    number: "v001",
    parent_id: null,
    change_kind: "首次生成",
    created_at: "",
    content_sha256: "hash",
    sources: [],
    content: {
      title: "待核验 · 氧化还原反应",
      goals: ["学习目标"],
      sections: [],
    },
    report: {
      draft: true,
      source_issues: [
        "未提供已核对的教材或教师用书（title、locator、evidence及verified=true）",
        "资料缺口：未提供教材页码",
        "原内容已标记待核验，不能自动升级为正式成果",
      ],
      review_required: [],
      statistics: { content_tables: 0, note_rows: 25 },
      validation: { passed: true },
    },
  };
  render(
    <OutlinePreview
      version={version}
      sessionId="session"
      onSources={vi.fn()}
    />,
  );
  expect(screen.getByRole("heading", { name: "氧化还原反应" })).toBeTruthy();
  expect(screen.getByText("资料缺口：未提供教材页码")).toBeTruthy();
  expect(screen.getByRole("button", { name: "查看来源" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "下载 Word" })).toBeTruthy();
  expect(screen.queryAllByText(/待核验|来源已核对|verified=true/)).toHaveLength(
    0,
  );
});

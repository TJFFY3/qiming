// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Conversation from "../components/Conversation";
import { defaultSettings, type Session, type Job } from "../services/api";
afterEach(cleanup);
test("repair errors show readable summary with technical details collapsed", () => {
  const session: Session = {
    id: "s",
    settings: defaultSettings(),
    messages: [],
    resources: [],
    sources: [],
    versions: [],
    jobs: [],
  };
  const job: Job = {
    id: "j",
    session_id: "s",
    kind: "generation",
    status: "failed",
    stages: [],
    version_id: null,
    created_at: new Date().toISOString(),
    error: "表格缺少表头，自动修复未成功，请重试。",
    error_detail: "$.outline.sections[3].blocks[3].headers[0]: 文本不能为空白",
  };
  render(
    <Conversation
      session={session}
      job={job}
      onVersion={vi.fn()}
      onSources={vi.fn()}
      onVersionSources={vi.fn()}
      onRetry={vi.fn()}
      onSuggestion={vi.fn()}
      busy={false}
    />,
  );
  expect(screen.getByText(job.error!)).toBeTruthy();
  expect(screen.getByText("查看错误详情")).toBeTruthy();
  expect(
    screen
      .getByText(job.error_detail!)
      .closest("details")
      ?.hasAttribute("open"),
  ).toBe(false);
  expect(screen.getByRole("button", { name: "重试" })).toBeTruthy();
});

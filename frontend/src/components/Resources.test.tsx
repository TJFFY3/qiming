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

test("library shows all knowledge chunks and PPT original rather than session recall", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        synced_at: "2026-10-19",
        chunk_count: 2,
        documents: [
          {
            id: "ppt",
            title: "课件.pptx",
            dataset_name: "全库",
            kind: "presentation",
            chunks: [
              {
                id: "one",
                title: "课件.pptx",
                category: "reference",
                locator: "片段1",
                evidence: "全库第一段",
                verified: false,
              },
              {
                id: "two",
                title: "课件.pptx",
                category: "reference",
                locator: "片段2",
                evidence: "未命中的第二段",
                verified: false,
              },
            ],
          },
        ],
      }),
    }),
  );
  render(
    <Resources
      sources={[
        {
          id: "hit",
          title: "仅检索命中",
          category: "reference",
          locator: "hit",
          evidence: "命中",
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
  fireEvent.click(await screen.findByRole("button", { name: /课件.pptx/ }));
  expect(
    screen.getByRole("link", { name: "下载原文件" }).getAttribute("href"),
  ).toBe("/api/library/ppt/original");
  expect(screen.queryByText("仅检索命中")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /片段2/ }));
  expect(screen.getByText("未命中的第二段")).toBeTruthy();
  vi.unstubAllGlobals();
});

test("large files expose later chunks without truncation", async () => {
  const chunks = Array.from({ length: 21 }, (_, i) => ({
    id: `c${i}`,
    title: "教材.pdf",
    category: "reference",
    locator: `片段 ${i + 1}`,
    evidence: `教材正文 ${i + 1}`,
    verified: false,
  }));
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        synced_at: "2026-10-19",
        chunk_count: 21,
        documents: [
          {
            id: "book",
            title: "教材.pdf",
            dataset_name: "教材库",
            kind: "document",
            chunks,
          },
        ],
      }),
    }),
  );
  render(
    <Resources
      sources={[]}
      resources={[]}
      onUpload={vi.fn()}
      onReview={vi.fn()}
      onClose={() => {}}
      busy={false}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: /教材.pdf/ }));
  expect(screen.queryByRole("button", { name: /片段 21/ })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /继续显示片段/ }));
  fireEvent.click(screen.getByRole("button", { name: /片段 21/ }));
  expect(screen.getByText("教材正文 21")).toBeTruthy();
  vi.unstubAllGlobals();
});

test("uploaded files can be deleted with visible failure feedback", async () => {
  const remove = vi.fn().mockRejectedValue(new Error("删除失败，请重试"));
  render(
    <Resources
      recall
      sources={[]}
      resources={[
        {
          id: "upload",
          title: "上传教材.txt",
          category: "textbook",
          locator: "上传原文",
          evidence: "内容",
          verified: false,
        },
      ]}
      onUpload={vi.fn()}
      onReview={vi.fn()}
      onDelete={remove}
      onClose={() => {}}
      busy={false}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "删除资料 上传教材.txt" }),
  );
  expect(await screen.findByRole("alert")).toHaveProperty(
    "textContent",
    "删除失败，请重试",
  );
  expect(remove).toHaveBeenCalledWith("upload");
});

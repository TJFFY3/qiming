// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Resources from "./Resources";
import PracticeResources from "../agents/timed-practice/Resources";
import CoursewareResources from "../agents/courseware/Resources";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const upload = {
  id: "upload",
  title: "本课教材.txt",
  category: "textbook",
  locator: "上传原文",
  evidence: "本课内容",
  verified: false,
};
const historical = {
  ...upload,
  id: "old",
  title: "历史教材",
  evidence: "历史内容",
};
const agents = [
  { name: "导学案", prefix: "/api", Component: Resources },
  {
    name: "限时练习",
    prefix: "/api/timed-practice",
    Component: PracticeResources,
  },
  {
    name: "互动课件",
    prefix: "/api/courseware",
    Component: CoursewareResources,
  },
];

test.each(agents)(
  "$name library uses the guide interaction and its own original-file endpoint",
  async ({ Component, prefix }) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        if (String(url) !== `${prefix}/library`)
          return Response.json({ detail: "错误的资料库接口" }, { status: 404 });
        return Response.json({
          synced_at: "2026-10-21",
          chunk_count: 1,
          documents: [
            {
              id: "book",
              title: "知识库教材.pdf",
              dataset_name: "教材库",
              kind: "document",
              chunks: [
                {
                  ...historical,
                  locator: "片段1",
                  evidence: "![装置图](https://example.com/apparatus.png)",
                },
              ],
            },
          ],
        });
      }),
    );
    render(
      <Component
        resources={[upload]}
        sources={[]}
        snapshot={false}
        busy={false}
        onUpload={vi.fn()}
        onDelete={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("dialog", { name: "资料库" })).toBeTruthy();
    expect(screen.getByText("添加本课参考资料")).toBeTruthy();
    fireEvent.click(
      await screen.findByRole("button", { name: /知识库教材.pdf/ }),
    );
    expect(
      screen.getByRole("link", { name: "下载原文件" }).getAttribute("href"),
    ).toBe(`${prefix}/library/book/original`);
    fireEvent.click(screen.getByRole("button", { name: /片段1/ }));
    expect(screen.getByRole("img", { name: "装置图" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "删除资料 本课教材.txt" }),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "完成" })).toBeTruthy();
  },
);

test.each(agents)(
  "$name source snapshot excludes later uploads and editing controls",
  ({ Component }) => {
    render(
      <Component
        resources={[upload]}
        sources={[historical]}
        snapshot
        busy={false}
        onUpload={vi.fn()}
        onDelete={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("dialog", { name: "当前版本 · 来源快照" }),
    ).toBeTruthy();
    expect(screen.queryByText("本课教材.txt")).toBeNull();
    expect(screen.queryByRole("button", { name: "选择文件" })).toBeNull();
    expect(screen.queryByRole("button", { name: /删除资料/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /历史教材/ }));
    expect(screen.getByText("历史内容")).toBeTruthy();
  },
);

test.each(agents)(
  "$name automatically syncs its own catalog and keeps it visible after a failed refresh",
  async ({ Component, prefix }) => {
    let synchronized = false;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url, init) => {
        if (String(url) === `${prefix}/library` && !init?.method) {
          return Response.json({
            documents: [],
            chunk_count: 0,
            synced_at: null,
          });
        }
        if (
          String(url) === `${prefix}/library/sync` &&
          init?.method === "POST"
        ) {
          if (synchronized)
            return Response.json(
              { detail: "同步失败，请重试" },
              { status: 503 },
            );
          synchronized = true;
          return Response.json({
            synced_at: "2026-10-21",
            chunk_count: 0,
            documents: [
              {
                id: "ppt",
                title: "Lesson.pptx",
                dataset_name: "教材库",
                kind: "presentation",
                chunks: [],
              },
            ],
          });
        }
        return Response.json({ detail: "错误的资料库接口" }, { status: 404 });
      }),
    );
    render(
      <Component
        resources={[]}
        sources={[]}
        snapshot={false}
        busy={false}
        onUpload={vi.fn()}
        onDelete={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(
      await screen.findByRole("button", { name: /Lesson.pptx/ }),
    ).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox", { name: "筛选知识库资料" }), {
      target: { value: "不匹配" },
    });
    expect(screen.queryByRole("button", { name: /Lesson.pptx/ })).toBeNull();
    fireEvent.change(screen.getByRole("textbox", { name: "筛选知识库资料" }), {
      target: { value: "lesson" },
    });
    fireEvent.click(screen.getByRole("button", { name: "同步知识库" }));
    expect(await screen.findByRole("alert")).toHaveProperty(
      "textContent",
      "同步失败，请重试",
    );
    expect(screen.getByRole("button", { name: /Lesson.pptx/ })).toBeTruthy();
  },
);

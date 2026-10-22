// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import CoursewareImage from "../components/CoursewareImage";

afterEach(cleanup);

test("original source image has caption and can be enlarged and closed with Escape", () => {
  render(
    <CoursewareImage
      src="/api/courseware/sessions/s/versions/v/images/abc"
      caption="实验装置原图"
    />,
  );
  expect(
    screen.getByRole("img", { name: "实验装置原图" }).getAttribute("src"),
  ).toContain("/api/courseware/");
  fireEvent.click(
    screen.getByRole("button", { name: "放大图片：实验装置原图" }),
  );
  expect(screen.getByRole("dialog", { name: "课件图片" })).toBeTruthy();
  fireEvent.keyDown(window, { key: "Escape" });
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("broken original image shows a clear fallback instead of a broken image", () => {
  render(<CoursewareImage src="/missing" caption="装置图" />);
  fireEvent.error(screen.getByRole("img"));
  expect(screen.getByRole("status").textContent).toContain("图片加载失败");
  expect(screen.queryByRole("button", { name: "放大图片：装置图" })).toBeNull();
});

test("illustrated slide displays the same version-bound image in preview and presentation", async () => {
  const { default: Preview } = await import("../components/Preview");
  const version = {
    id: "v",
    number: "v001",
    parent_id: null,
    created_at: "",
    sources: [],
    content: {
      title: "图文课件",
      slides: [
        {
          title: "实验观察",
          stage: "探",
          paragraphs: ["观察现象"],
          image_id: "a".repeat(24),
          image_caption: "实验原图",
        },
      ],
    },
    report: {
      draft: false,
      page_count: 1,
      source_issues: [],
      conflicts: [],
      visual_review: "",
      validation: { passed: true, warnings: [] },
    },
  };
  render(<Preview sid="s" version={version} />);
  expect(
    screen.getByRole("img", { name: "实验原图" }).getAttribute("src"),
  ).toContain("/sessions/s/versions/v/images/");
  fireEvent.click(screen.getByRole("button", { name: "演示" }));
  expect(screen.getAllByRole("img", { name: "实验原图" })).toHaveLength(2);
});

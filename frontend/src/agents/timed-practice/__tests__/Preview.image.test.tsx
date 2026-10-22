// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Preview from "../components/Preview";
import type { Version } from "../domain/types";

afterEach(cleanup);

function version(): Version {
  return {
    id: "v1",
    number: "v001",
    parent_id: null,
    created_at: "2026-10-21",
    sources: [],
    report: {
      draft: false,
      source_issues: [],
      review_required: [],
      validation: { passed: true },
    },
    content: {
      title: "带图限时练习",
      duration: 20,
      total_score: 10,
      written: [],
      optional: [],
      source_gaps: [],
      conflicts: [],
      choice: [
        {
          stem: "观察实验装置，选出正确操作。",
          options: ["甲", "乙", "丙", "丁"],
          answer: "B",
          explanation: "操作顺序如图。",
          score: 10,
          minutes: 2,
          difficulty: "基础",
          origin: "new",
          source_ids: [],
          work_lines: 2,
          images: [
            {
              image_id: "stem-image",
              caption: "实验装置 <b>原图</b>",
              placement: "stem",
            },
            {
              image_id: "option-image",
              caption: "选项乙示意图",
              placement: "option_B",
            },
            {
              image_id: "answer-image",
              caption: "解析示意图",
              placement: "explanation",
            },
          ],
        },
      ],
    },
  };
}

test("student paper shows question and option images without leaking answer images", () => {
  render(
    <Preview version={version()} sessionId="session-1" onSources={vi.fn()} />,
  );
  const image = screen.getByRole("img", { name: "实验装置 <b>原图</b>" });
  expect(image.getAttribute("src")).toBe(
    "/api/timed-practice/sessions/session-1/versions/v1/images/stem-image",
  );
  expect(image.closest("figure")?.querySelector("b")).toBeNull();
  expect(
    screen.getByRole("img", { name: "选项乙示意图" }).closest("li")
      ?.textContent,
  ).toContain("乙");
  expect(screen.queryByRole("img", { name: "解析示意图" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "答案与解析" }));
  expect(screen.getByRole("img", { name: "解析示意图" })).toBeTruthy();
  expect(screen.queryByRole("img", { name: "选项乙示意图" })).toBeNull();
});

test("failed original image retains its caption and shows a visible fallback", () => {
  render(
    <Preview version={version()} sessionId="session-1" onSources={vi.fn()} />,
  );
  const image = screen.getByRole("img", { name: "实验装置 <b>原图</b>" });
  const figure = image.closest("figure")!;
  fireEvent.error(image);
  expect(within(figure).getByRole("status").textContent).toContain(
    "图片加载失败",
  );
  expect(figure.querySelector("figcaption")?.textContent).toBe(
    "实验装置 <b>原图</b>",
  );
});

test("text-only historical questions still render without image fields", () => {
  const value = version();
  delete value.content.choice[0].images;
  render(<Preview version={value} sessionId="session-1" onSources={vi.fn()} />);
  expect(screen.getByText("观察实验装置，选出正确操作。")).toBeTruthy();
  expect(screen.queryByRole("img")).toBeNull();
});

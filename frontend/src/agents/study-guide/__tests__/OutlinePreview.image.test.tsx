// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import type { Version } from "../services/api";
import OutlinePreview from "../components/OutlinePreview";

afterEach(cleanup);

function version(): Version {
  return {
    id: "version-2",
    number: "v002",
    parent_id: "version-1",
    change_kind: "修订",
    created_at: "2026-10-21",
    content_sha256: "hash",
    content: {
      title: "氧化还原反应",
      goals: ["观察实验"],
      sections: [{
        id: "section-1",
        title: "实验记录",
        blocks: [{ id: "p1", type: "paragraph", content: "观察 [H2O]" }, {
          id: "t1", type: "table", headers: ["现象"], rows: [["产生气泡"]],
        }],
      }],
    },
    sources: [],
    report: {
      draft: false,
      source_issues: [],
      review_required: [],
      statistics: { content_tables: 1, note_rows: 25 },
      validation: { passed: true },
    },
  };
}

test("renders original image from its session and version with a plain-text caption", () => {
  const value = version();
  value.content.sections[0].blocks.push({
    id: "figure-1", type: "image", image_id: "original-1", caption: "实验图 <b>原图</b>",
  });
  render(<OutlinePreview version={value} sessionId="session-1" onSources={() => {}} />);
  const image = screen.getByRole("img", { name: "实验图 <b>原图</b>" });
  expect(image.getAttribute("src")).toBe("/api/sessions/session-1/versions/version-2/images/original-1");
  expect(image.closest("figure")?.querySelector("figcaption")?.textContent).toBe("实验图 <b>原图</b>");
  expect(image.closest("figure")?.querySelector("b")).toBeNull();
});

test("shows a visible fallback and keeps the caption when an original image fails to load", () => {
  const value = version();
  value.content.sections[0].blocks.push({
    id: "figure-1", type: "image", image_id: "original-1", caption: "实验装置",
  });
  render(<OutlinePreview version={value} sessionId="session-1" onSources={() => {}} />);
  fireEvent.error(screen.getByRole("img", { name: "实验装置" }));
  expect(screen.getByRole("status").textContent).toContain("图片加载失败");
  expect(screen.getByText("实验装置").tagName).toBe("FIGCAPTION");
  expect(screen.queryByRole("img")).toBeNull();
});

test("preserves paragraph chemistry and table rendering in older outlines", () => {
  const { container } = render(<OutlinePreview version={version()} sessionId="session-1" onSources={() => {}} />);
  expect(container.querySelector("p sub")?.textContent).toBe("2");
  expect(screen.getByRole("columnheader", { name: "现象" })).toBeTruthy();
  expect(screen.getByRole("cell", { name: "产生气泡" })).toBeTruthy();
});

// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import OutlinePreview, { Rich } from "./OutlinePreview";
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

test("legacy reaction shows subscripts and a stacked condition instead of markup", () => {
  const { container } = render(
    <Rich value="<br>CaCO3 ===高温=== CaO + CO2↑" />,
  );
  expect(
    Array.from(container.querySelectorAll("sub"), (n) => n.textContent),
  ).toEqual(["3", "2"]);
  expect(container.querySelector(".condition small")?.textContent).toBe("高温");
  expect(container.textContent).not.toContain("===高温===");
  expect(container.textContent).not.toContain("<br>");
  expect(container.querySelector("br")).not.toBeNull();
});

test("normalizes legacy rich runs while preserving coefficients and emphasis", () => {
  const { container } = render(
    <Rich value={[{ text: "2H2O ===通电=== 2H2 + O2↑", bold: true }]} />,
  );
  expect(
    Array.from(container.querySelectorAll("sub"), (n) => n.textContent),
  ).toEqual(["2", "2", "2"]);
  expect(container.textContent).toContain("2H2O");
  expect(container.querySelector(".condition small")?.textContent).toBe("通电");
  expect(container.querySelector('[style*="700"]')).not.toBeNull();
});

test("preserves existing chemistry notation and ordinary text", () => {
  const { container } = render(
    <Rich
      value={[
        { text: "[SO4^2-]" },
        { text: "高温", condition: true },
        { text: "===重点===" },
      ]}
    />,
  );
  expect(container.querySelector("sup")?.textContent).toBe("2-");
  expect(container.querySelectorAll(".condition")).toHaveLength(1);
  expect(container.textContent).toContain("===重点===");
});

test("recognizes a condition split across styled rich runs", () => {
  const { container } = render(
    <Rich
      value={[
        { text: "CaCO3 " },
        { text: "===高", bold: true },
        { text: "温===" },
        { text: " CaO + CO2↑", italic: true },
      ]}
    />,
  );
  expect(container.querySelector(".condition small")?.textContent).toBe("高温");
  expect(
    Array.from(container.querySelectorAll("sub"), (n) => n.textContent),
  ).toEqual(["3", "2"]);
  expect(container.textContent).not.toContain("===高");
  expect(container.querySelector('[style*="italic"]')).not.toBeNull();
});

test("formula split across styles retains a baseline coefficient and a subscript atom count", () => {
  const { container } = render(
    <Rich
      value={[{ text: "2H", bold: true }, { text: "2O ===通电=== 2H2 + O2↑" }]}
    />,
  );
  expect(
    Array.from(container.querySelectorAll("sub"), (n) => n.textContent),
  ).toEqual(["2", "2", "2"]);
  expect(container.querySelector('[style*="700"]')?.textContent).toBe("2H");
});

test.each([
  "2KMnO4 △→ K2MnO4 + MnO2 + O2↑",
  "2KMnO4 Δ→ K2MnO4 + MnO2 + O2↑",
  "[2KMnO4] △→ [K2MnO4] + [MnO2] + [O2]↑",
])(
  "formats heating arrow and keeps coefficient out of subscripts: %s",
  (value) => {
    const { container } = render(<Rich value={value} />);
    expect(
      Array.from(container.querySelectorAll("sub"), (n) => n.textContent),
    ).toEqual(["4", "2", "4", "2", "2"]);
    expect(container.querySelector(".condition small")?.textContent).toBe("△");
    expect(container.textContent?.startsWith("2K")).toBe(true);
    expect(container.textContent).not.toContain("→");
  },
);

import { expect, test } from "vitest";
import { sourceNotes, sourceTitle } from "./sourceDisplay";

test("legacy source labels are removed while missing source details remain visible", () => {
  expect(
    sourceNotes([
      "来源未核实，需核对后导出",
      "教材页码尚待核对",
      "资料缺口：未提供教师用书",
      "原内容已标记待核验，不能自动升级为正式成果",
    ]),
  ).toEqual(["教材页码信息待补充", "资料缺口：未提供教师用书"]);
  expect(sourceTitle("（待核验草案）氧化还原反应")).toBe("氧化还原反应");
  expect(sourceTitle("氧化还原反应（待核验）")).toBe("氧化还原反应");
});

test("repeated review prefixes and trailing badges are removed", () => {
  expect(sourceTitle("待核验 · 待核验-氧化还原反应 · 待核验")).toBe(
    "氧化还原反应",
  );
});

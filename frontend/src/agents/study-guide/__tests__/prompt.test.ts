import { expect, test } from "vitest";
import { defaultOptions, defaultSettings } from "../services/api";
import {
  applyOptimization,
  ensureOptimization,
  formatLessonPrompt,
} from "../domain/prompt";
test("all optimization fields become visible Chinese prompt text and repeated apply replaces prior values", () => {
  const options = {
    ...defaultOptions(),
    scope: "仅第一课时",
    duration: "15 分钟",
    tasks: "3 个任务",
    difficulty: "基础为主",
    hints: "详细提示",
    focus: ["概念理解", "化学方程式"],
    extra: "学生基础较弱",
  };
  const first = applyOptimization("以生活情境导入", options);
  for (const value of [
    "学习范围：仅第一课时",
    "自学用时：15 分钟",
    "任务数量：3 个任务",
    "内容难度：基础为主",
    "提示详略：详细提示",
    "本课重点：概念理解、化学方程式",
    "补充要求：学生基础较弱",
  ])
    expect(first).toContain(value);
  const updated = applyOptimization(first, { ...options, duration: "20 分钟" });
  expect(updated).toContain("以生活情境导入");
  expect(updated).not.toContain("15 分钟");
  expect(updated.match(/【优化提示】/g)).toHaveLength(1);
  expect(
    ensureOptimization(updated.replace("20 分钟", "25 分钟"), options),
  ).toContain("25 分钟");
});

test("lesson context appears before optimization and assembly is idempotent", () => {
  const settings = { ...defaultSettings(), chapter: "钠及其化合物" };
  const prompt = formatLessonPrompt(
    applyOptimization("请根据本课内容生成一份导学案。", settings.options),
    settings,
  );
  expect(prompt.indexOf("学科：化学")).toBeLessThan(
    prompt.indexOf("【优化提示】"),
  );
  expect(prompt).toContain("课时：第一课时\n【优化提示】");
  expect(formatLessonPrompt(prompt, settings)).toBe(prompt);
});

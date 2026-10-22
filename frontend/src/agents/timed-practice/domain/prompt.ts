import type { Options, Settings } from "./types";
import { assembleLessonPrompt } from "../../../lessonPrompt";
export const START = "【限时练习优化设置】",
  END = "【限时练习优化设置结束】";
export function applyOptimization(prompt: string, options: Options) {
  const body = prompt
    .replace(/【限时练习优化设置】[\s\S]*?【限时练习优化设置结束】/g, "")
    .trim();
  return `${body || "请根据本课内容生成一份限时练习。"}\n\n${START}\n用时：${options.duration}\n满分：${options.score}\n题型和数量：${options.questions}\n题目难度：${options.difficulty}\n出题方式：${options.origin}\n重点练什么：${options.focus.join("、")}\n补充要求：${options.extra || "无"}\n${END}`;
}

export function formatLessonPrompt(prompt: string, settings: Settings) {
  const text = prompt.trim() || "请根据本课内容生成一份限时练习。";
  const withOptions =
    text.includes(START) && text.includes(END)
      ? text
      : applyOptimization(text, settings.options);
  return assembleLessonPrompt(
    withOptions,
    settings,
    /【限时练习优化设置】[\s\S]*?【限时练习优化设置结束】/,
  );
}

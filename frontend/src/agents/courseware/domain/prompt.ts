import type { CoursewareOptions, CoursewareSettings } from "./types";
import { assembleLessonPrompt } from "../../../lessonPrompt";
const START = "【课件优化提示】",
  END = "【课件优化结束】";
export function applyOptimization(prompt: string, options: CoursewareOptions) {
  const base = prompt
    .replace(/【课件优化提示】[\s\S]*?【课件优化结束】/g, "")
    .trim();
  return `${base || "请根据本课内容生成一份互动课件。"}\n\n${START}\n教学内容：${options.scope}\n课堂时长：${options.duration}\n课件页数：${options.pages}\n课堂练习：${options.exercises}\n上课方式：${options.teaching}\n本课重点：${options.focus.join("、")}\n补充要求：${options.extra || "无"}\n${END}`;
}

export function formatLessonPrompt(
  prompt: string,
  settings: CoursewareSettings,
) {
  const text = prompt.trim() || "请根据本课内容生成一份互动课件。";
  const withOptions =
    text.includes(START) && text.includes(END)
      ? text
      : applyOptimization(text, settings.options);
  return assembleLessonPrompt(
    withOptions,
    settings,
    /【课件优化提示】[\s\S]*?【课件优化结束】/,
  );
}

import type { Options } from "../services/api";
import { assembleLessonPrompt } from "../../../lessonPrompt";
const START = "【优化提示】";
const END = "【优化提示结束】";
export function applyOptimization(prompt: string, options: Options): string {
  const instruction = prompt
    .replace(/\n?【优化提示】\n[\s\S]*?【优化提示结束】/g, "")
    .trim();
  const lines = [
    `学习范围：${options.scope}`,
    `自学用时：${options.duration}`,
    `任务数量：${options.tasks}`,
    `内容难度：${options.difficulty}`,
    `提示详略：${options.hints}`,
    `本课重点：${options.focus.join("、") || "按本课安排（默认）"}`,
    `补充要求：${options.extra.trim() || "无额外要求"}`,
    "重点仅表示加强，不删除其他必学内容；默认项目按本课内容安排，不预设固定用时和题量。",
  ];
  return [instruction, `${START}\n${lines.join("\n")}\n${END}`]
    .filter(Boolean)
    .join("\n\n");
}
export function ensureOptimization(prompt: string, options: Options): string {
  // Once filled into the editor, teachers can edit the visible instruction directly.
  return prompt.includes(START) && prompt.includes(END)
    ? prompt
    : applyOptimization(prompt, options);
}

export function formatLessonPrompt(
  prompt: string,
  settings: import("../services/api").Settings,
): string {
  return assembleLessonPrompt(
    ensureOptimization(prompt, settings.options),
    settings,
    /【优化提示】\n[\s\S]*?【优化提示结束】/,
  );
}

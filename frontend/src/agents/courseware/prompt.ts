import type { CoursewareOptions } from "./types";
const START = "【课件优化提示】",
  END = "【课件优化结束】";
export function applyOptimization(prompt: string, options: CoursewareOptions) {
  const start = prompt.indexOf(START),
    end = prompt.indexOf(END, start);
  const base = (
    start >= 0 && end >= start
      ? prompt.slice(0, start) + prompt.slice(end + END.length)
      : prompt
  ).trim();
  return `${base || "请根据本课内容生成互动课件。"}\n\n${START}\n教学内容：${options.scope}\n课堂时长：${options.duration}\n课件页数：${options.pages}\n课堂练习：${options.exercises}\n上课方式：${options.teaching}\n本课重点：${options.focus.join("、")}\n补充要求：${options.extra || "无"}\n${END}`;
}

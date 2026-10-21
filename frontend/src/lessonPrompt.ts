export type LessonContext = {
  edition: string;
  grade: string;
  chapter: string;
  period: string;
};

export function assembleLessonPrompt(
  prompt: string,
  settings: LessonContext,
  optimizationPattern: RegExp,
): string {
  const block = prompt.match(optimizationPattern)?.[0];
  const instruction = prompt
    .replace(new RegExp(optimizationPattern.source, "g"), "")
    .replace(
      /^学科：化学\n教材版本：[^\n]*\n年级：[^\n]*\n章节 \/ 知识点：[^\n]*\n课时：[^\n]*(?:\n|$)/gm,
      "",
    )
    .trim();
  const context = `学科：化学\n教材版本：${settings.edition}\n年级：${settings.grade}\n章节 / 知识点：${settings.chapter}\n课时：${settings.period}`;
  return [instruction, [context, block].filter(Boolean).join("\n")]
    .filter(Boolean)
    .join("\n\n");
}

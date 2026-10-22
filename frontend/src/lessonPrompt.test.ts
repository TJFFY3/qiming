import { expect, test } from "vitest";
import { defaultSettings as guideSettings } from "./agents/study-guide/services/api";
import { defaultSettings as coursewareSettings } from "./agents/courseware/domain/types";
import { defaultSettings as practiceSettings } from "./agents/timed-practice/domain/types";
import { formatLessonPrompt as guidePrompt } from "./agents/study-guide/domain/prompt";
import { formatLessonPrompt as coursewarePrompt } from "./agents/courseware/domain/prompt";
import { formatLessonPrompt as practicePrompt } from "./agents/timed-practice/domain/prompt";
import type { LessonContext } from "./lessonPrompt";

const agents = [
  {
    name: "导学案",
    format: (prompt: string, lesson: Partial<LessonContext> = {}) =>
      guidePrompt(prompt, { ...guideSettings(), ...lesson }),
    marker: "【优化提示】",
    end: "【优化提示结束】",
    option: "自学用时",
  },
  {
    name: "互动课件",
    format: (prompt: string, lesson: Partial<LessonContext> = {}) =>
      coursewarePrompt(prompt, { ...coursewareSettings(), ...lesson }),
    marker: "【课件优化提示】",
    end: "【课件优化结束】",
    option: "课堂时长",
  },
  {
    name: "限时练习",
    format: (prompt: string, lesson: Partial<LessonContext> = {}) =>
      practicePrompt(prompt, { ...practiceSettings(), ...lesson }),
    marker: "【限时练习优化设置】",
    end: "【限时练习优化设置结束】",
    option: "用时",
  },
] as const;

test.each(agents)(
  "$name submission includes the selected lesson before optimization",
  ({ name, format, marker }) => {
    const instruction = `请根据本课内容生成一份${name}。`;
    const prompt = format(instruction);
    expect(prompt).toContain(
      `${instruction}\n\n学科：化学\n教材版本：人教版 必修第一册\n年级：高一\n章节 / 知识点：第三节 氧化还原反应\n课时：第一课时\n${marker}`,
    );
  },
);

test.each(agents)(
  "$name retry updates stale lesson fields without duplicating context or overwriting edited optimization",
  ({ format, marker, end, option }) => {
    const first = format(
      `增加课堂互动\n\n${marker}\n${option}：25 分钟\n${end}`,
    );
    const changed = {
      chapter: "钠及其化合物",
      period: "第二课时",
    };
    const retried = format(first, changed);
    expect(retried).toContain("增加课堂互动");
    expect(retried).toContain(`${option}：25 分钟`);
    expect(retried).toContain("章节 / 知识点：钠及其化合物\n课时：第二课时");
    expect(retried).not.toContain("第三节 氧化还原反应");
    expect(retried.match(/学科：化学/g)).toHaveLength(1);
    expect(retried.split(marker)).toHaveLength(2);
    expect(format(retried, changed)).toBe(retried);
  },
);

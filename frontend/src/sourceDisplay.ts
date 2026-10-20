// Verification metadata stays in saved records; source panels show useful source details.
export const sourceNotes = (issues: string[] = []) =>
  issues
    .filter(
      (issue) =>
        !/verified\s*=\s*true|未提供已核对的教材或教师用书|原内容已标记待核验|来源未核实|缺少已核实|来源verified/.test(
          issue,
        ),
    )
    .map((issue) =>
      issue.replace(
        /(?:尚待|尚未|需|需要)?核对|待核验|待验证|未核验/g,
        "信息待补充",
      ),
    );
export const sourceTitle = (title: string) => {
  let value = title;
  while (true) {
    const cleaned = value
      .replace(
        /^\s*(?:[（(\[]\s*)?(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?)(?:\s*[）)\]])?[\s·：:\-—]*/,
        "",
      )
      .replace(
        /\s*(?:[（(\[]\s*(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?)\s*[）)\]]|[·：:\-—]\s*(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?))\s*$/,
        "",
      );
    if (cleaned === value) return cleaned;
    value = cleaned;
  }
};

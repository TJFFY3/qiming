// Verification metadata stays in saved records; source panels show only useful source notes.
export const sourceNotes = (issues: string[] = []) =>
  issues.filter(
    (issue) =>
      !/verified\s*=\s*true|未提供已核对的教材或教师用书|原内容已标记待核验/.test(
        issue,
      ),
  );
export const sourceTitle = (title: string) =>
  title.replace(/^\s*待核验(?:草案)?(?:\s*[·：:\-]\s*|\s+)/, "");

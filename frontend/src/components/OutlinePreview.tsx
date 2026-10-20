import type { ReactNode } from "react";
import { Download, FileText, CheckCircle2, ExternalLink } from "lucide-react";
import { sourceNotes, sourceTitle } from "../sourceDisplay";
import { fileUrl, type RichText, type Run, type Version } from "../api";
import { chemistryRuns } from "../chemistryFormat";
function formula(value: string): ReactNode {
  const charge = value.match(/(?:\^([0-9]*[+-])|([+-]))$/);
  const text = charge ? value.slice(0, charge.index) : value;
  return (
    <>
      {text
        .split(/(\d+)/)
        .map((v, i) => (/^\d+$/.test(v) ? <sub key={i}>{v}</sub> : v))}
      {charge && <sup>{charge[1] || charge[2]}</sup>}
    </>
  );
}
function marked(text: string): ReactNode {
  return text.split(/(\[[^\[\]]+\])/).map((x, i) =>
    x.startsWith("[") && x.endsWith("]") ? (
      <span key={i}>{formula(x.slice(1, -1))}</span>
    ) : (
      x.split("\n").map((line, j) => (
        <span key={j}>
          {j > 0 && <br />}
          {line}
        </span>
      ))
    ),
  );
}
function RunText({ run }: { run: Run }) {
  let body: ReactNode = marked(run.text);
  if (run.isotope)
    body = (
      <>
        <span className="isotope">
          <sup>{run.isotope.mass}</sup>
          <sub>{run.isotope.atomic}</sub>
        </span>
        {body}
      </>
    );
  if (run.condition)
    body = (
      <span className="condition">
        <small>{body}</small>
        <span>=====</span>
      </span>
    );
  if (run.sub) body = <sub>{body}</sub>;
  else if (run.sup || run.charge) body = <sup>{body}</sup>;
  return (
    <span
      style={{
        fontWeight: run.bold ? 700 : undefined,
        fontStyle: run.italic ? "italic" : undefined,
        textDecoration: run.underline ? "underline" : undefined,
      }}
    >
      {body}
    </span>
  );
}
export function Rich({ value }: { value: RichText }) {
  value = chemistryRuns(value);
  return (
    <>
      {Array.isArray(value)
        ? value.map((r, i) => <RunText key={i} run={r} />)
        : value
          ? marked(value)
          : "\u00a0"}
    </>
  );
}
export default function OutlinePreview({
  version,
  sessionId,
  onSources,
}: {
  version: Version;
  sessionId: string;
  onSources: () => void;
}) {
  const notes = sourceNotes(version.report.source_issues);
  return (
    <article className="document-card">
      <header className="document-toolbar">
        <span>
          <FileText size={20} />
          导学案 <b>{version.number}</b>
        </span>
        <div>
          <button className="text-button" onClick={onSources}>
            查看来源
            <ExternalLink size={14} />
          </button>
          <a
            className="button primary small"
            href={fileUrl(sessionId, version.id)}
          >
            <Download size={16} />
            下载 Word
          </a>
        </div>
      </header>
      <div className="document-status">
        <span>
          <CheckCircle2 size={14} />
          结构检查通过
        </span>
        <span>
          {version.change_kind} · {version.report.statistics.content_tables}{" "}
          个教学表格
        </span>
      </div>
      {!!notes.length && (
        <details className="source-issues">
          <summary>资料说明（{notes.length}）</summary>
          <ul>
            {notes.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </details>
      )}
      <div className="paper-preview">
        <h2>{sourceTitle(version.content.title)}</h2>
        <p className="student-line">
          班级 __________　姓名 __________　小组 __________
        </p>
        <h3>【学习目标】</h3>
        <ol>
          {version.content.goals.map((g, i) => (
            <li key={i}>
              <Rich value={g} />
            </li>
          ))}
        </ol>
        <h3>【基础自学】</h3>
        {version.content.sections.map((s) => (
          <section key={s.id}>
            {s.group && <h3>{s.group}</h3>}
            <h4>{s.title}</h4>
            {s.blocks.map((b) =>
              b.type === "paragraph" ? (
                <p key={b.id}>
                  <Rich value={b.content} />
                </p>
              ) : (
                <div className="table-scroll" key={b.id}>
                  <table>
                    <thead>
                      <tr>
                        {b.headers.map((h, i) => (
                          <th key={i}>
                            <Rich value={h} />
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {b.rows.map((r, i) => (
                        <tr key={i}>
                          {r.map((c, j) => (
                            <td key={j}>
                              <Rich value={c} />
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ),
            )}
          </section>
        ))}
        {version.content.thinking?.length ? (
          <>
            <h3>【思考与交流】</h3>
            {version.content.thinking.map((t, i) => (
              <p key={i}>
                <Rich value={t} />
              </p>
            ))}
          </>
        ) : null}
        {version.content.schedule_note && (
          <p>{version.content.schedule_note}</p>
        )}
        <h3>【笔记区域】</h3>
        <div className="note-lines">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} />
          ))}
        </div>
        <p className="preview-note">
          此处为内容预览，Word 中保留完整 25 行笔记区。
        </p>
      </div>
      <footer className="document-footnote">
        请在 Word / WPS 中复核化学符号、分页和答题空间。结构检查不替代教学审核。
      </footer>
    </article>
  );
}

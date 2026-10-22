import type { ReactNode } from "react";
import type { RichText } from "../domain/types";
import type { Run as SharedRun } from "../../study-guide/services/api";
import { chemistryRuns, markChemicalFormulas } from "../../../chemistryFormat";
function marked(text: string): ReactNode {
  return text.split(/(\[[^\[\]]+\])/g).map((part, i) => {
    if (!part.startsWith("["))
      return (
        <span key={i}>
          {part.split("\n").map((line, j) => (
            <span key={j}>
              {j > 0 && <br />}
              {line}
            </span>
          ))}
        </span>
      );
    const value = part.slice(1, -1),
      match = value.match(/(?:\^([\d]*[+-])|([+-]))$/),
      base = match ? value.slice(0, match.index) : value;
    return (
      <span key={i}>
        {base
          .split(/(\d+)/)
          .map((v, j) => (/^\d+$/.test(v) ? <sub key={j}>{v}</sub> : v))}
        {match && <sup>{match[1] || match[2]}</sup>}
      </span>
    );
  });
}
function Fragment({ run }: { run: SharedRun }) {
  let body: ReactNode = marked(run.text);
  if (run.isotope)
    body = (
      <>
        <span className="tp-isotope">
          <sup>{run.isotope.mass}</sup>
          <sub>{run.isotope.atomic}</sub>
        </span>
        {body}
      </>
    );
  if (run.condition)
    body = (
      <span className="tp-condition">
        <small>{marked(markChemicalFormulas(run.text))}</small>
        <span>=====</span>
      </span>
    );
  if (run.sub) body = <sub>{body}</sub>;
  if (run.sup || run.charge) body = <sup>{body}</sup>;
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
export default function Rich({ value }: { value: RichText }) {
  const normalized = chemistryRuns(value);
  if (!normalized) return null;
  return (
    <>
      {Array.isArray(normalized)
        ? normalized.map((r, i) => <Fragment key={i} run={r} />)
        : marked(normalized)}
    </>
  );
}

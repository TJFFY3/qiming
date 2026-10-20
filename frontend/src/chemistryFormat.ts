import type { RichText, Run } from "./api";

const elements =
  "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split(
    " ",
  );
const atom = `(?:${elements.sort((a, b) => b.length - a.length).join("|")})\\d*`;
const formula = new RegExp(`^(?:${atom}|\\((?:${atom})+\\)\\d*)+$`);
const tokens = () =>
  /\[[^\[\]]+\]|(?<![A-Za-z_\[])([A-Z][A-Za-z0-9()]*)(?![A-Za-z0-9_\]^]|[+-](?:\s|$))/g;
const hasFormula = (text: string) =>
  Array.from(text.matchAll(tokens())).some((m) =>
    formula.test(m[1] || m[0].slice(1, -1)),
  );
export const markChemicalFormulas = (text: string) =>
  text.replace(tokens(), (all, bare: string | undefined) =>
    bare && formula.test(bare) ? `[${bare}]` : all,
  );

const conditionPattern =
  /[=═→⟶]*[ \t]*(?:[（(]((?:MnO2|二氧化锰|催化剂)(?:[ ,，、/]*(?:△|Δ|加热))?)[)）]|(MnO2[,，、/]*(?:△|Δ|加热))|(点燃|通电|高温|加热|△|Δ))[ \t]*[=═→⟶]*/g;

function equationSides(text: string, start: number, end: number) {
  const leftToken = text
    .slice(0, start)
    .replace(/[（(](?:浓|稀)[)）][ \t]*$/, "")
    .match(/(\[[^\]]+\]|[A-Z][A-Za-z0-9()]*(?:[↑↓])?)[ \t]*$/)?.[1];
  const rightToken = text
    .slice(end)
    .match(/^[ \t]*(?:\d*)?(\[[^\]]+\]|[A-Z][A-Za-z0-9()]*)/)?.[1];
  const formulaBody = (token: string | undefined) =>
    token
      ?.replace(/^[\[]|[\]]$/g, "")
      .replace(/^\d+/, "")
      .replace(/[↑↓]$/, "");
  const left = formulaBody(leftToken);
  const right = formulaBody(rightToken);
  return !!left && !!right && formula.test(left) && formula.test(right);
}

function conditionLabel(match: RegExpMatchArray) {
  return (match[1] || match[2] || match[3] || "△")
    .replace(/Δ/g, "△")
    .replace(/[,，/]/g, "、");
}

const coefficient = (text: string) =>
  text.replace(
    /\[(\d+)([A-Z][A-Za-z0-9()]*)\]/g,
    (all, count: string, body: string) =>
      formula.test(body) ? `${count}[${body}]` : all,
  );

function legacyRuns(input: string): string | Run[] {
  return styledGroup([
    { text: coefficient(input.replace(/<br\s*\/?>/gi, "\n")) },
  ]);
}

/** Display compatibility for saved versions; never edits their stored content. */
export function chemistryRuns(value: RichText): RichText {
  if (typeof value === "string") return legacyRuns(value);
  if (!Array.isArray(value)) return value;
  const result: Run[] = [];
  let group: Run[] = [];
  const flush = () => {
    result.push(...styledGroup(group));
    group = [];
  };
  for (const run of value) {
    if (run.condition || run.sub || run.sup || run.charge || run.isotope) {
      flush();
      result.push(run);
    } else group.push(run);
  }
  flush();
  return result;
}

function styledGroup(input: Run[]): Run[] {
  const runs = input.map((r) => ({
    ...r,
    text: coefficient(r.text.replace(/<br\s*\/?>/gi, "\n")),
  }));
  const text = runs.map((r) => r.text).join("");
  const matches: {
    start: number;
    end: number;
    labelStart: number;
    label: string;
  }[] = [];
  const lines: [number, number][] = [];
  let offset = 0;
  for (const line of text.split("\n")) {
    conditionPattern.lastIndex = 0;
    const conditionMatches: RegExpMatchArray[] = [];
    for (const match of line.matchAll(conditionPattern)) {
      if (equationSides(line, match.index!, match.index! + match[0].length))
        conditionMatches.push(match);
    }
    const equation =
      conditionMatches.length > 0 ||
      (/[=═→⟶]/.test(line) && hasFormula(line));
    if (equation) {
      lines.push([offset, offset + line.length]);
      for (const m of conditionMatches)
        matches.push({
          start: offset + m.index!,
          end: offset + m.index! + m[0].length,
          labelStart:
            offset + m.index! + m[0].indexOf(m[1] || m[2] || m[3]),
          label: conditionLabel(m),
        });
    }
    offset += line.length + 1;
  }
  if (!lines.length)
    return runs.map((run) => ({
      ...run,
      text: markChemicalFormulas(run.text),
    }));
  offset = 0;
  const spans = runs.map((run) => {
    const start = offset;
    offset += run.text.length;
    return { start, end: offset, run };
  });
  const result: Run[] = [];
  const crossing = Array.from(text.matchAll(tokens())).filter(
    (m) =>
      m[1] &&
      formula.test(m[1]) &&
      spans.some((s) => m.index! < s.end && s.end < m.index! + m[0].length),
  );
  const piece = (run: Run, lo: number, hi: number) => {
    const cuts = new Set([lo, hi]);
    const overlapping = crossing.filter(
      (m) => m.index! < hi && m.index! + m[0].length > lo,
    );
    for (const m of overlapping)
      for (
        let i = Math.max(lo, m.index!);
        i <= Math.min(hi, m.index! + m[0].length);
        i++
      )
        cuts.add(i);
    const points = Array.from(cuts).sort((a, b) => a - b);
    for (let i = 0; i < points.length - 1; i++) {
      const start = points[i],
        end = points[i + 1],
        fragment = text.slice(start, end);
      const inside = overlapping.some(
        (m) => m.index! <= start && start < m.index! + m[0].length,
      );
      result.push({
        ...run,
        text: inside
          ? fragment
          : markChemicalFormulas(fragment),
        ...(inside && /^\d+$/.test(fragment) ? { sub: true } : {}),
      });
    }
  };
  const gap = (start: number, end: number) => {
    for (const span of spans) {
      const lo = Math.max(start, span.start),
        hi = Math.min(end, span.end);
      if (lo >= hi) continue;
      const cuts = Array.from(
        new Set([lo, hi, ...lines.flat().filter((p) => lo < p && p < hi)]),
      ).sort((a, b) => a - b);
      for (let i = 0; i < cuts.length - 1; i++)
        piece(span.run, cuts[i], cuts[i + 1]);
    }
  };
  let position = 0;
  for (const m of matches) {
    gap(position, m.start);
    const style = spans.find(
      (s) => s.start <= m.labelStart && m.labelStart < s.end,
    )!.run;
    result.push({ ...style, text: m.label, condition: true });
    position = m.end;
  }
  gap(position, text.length);
  const merged: Run[] = [];
  for (const run of result) {
    const previous = merged.at(-1);
    const style = ({ text: _text, ...rest }: Run) => JSON.stringify(rest);
    if (previous && !run.condition && style(previous) === style(run))
      previous.text += run.text;
    else merged.push(run);
  }
  return merged;
}

// Neutral chemistry typography types: shared without depending on any Agent.
export type Run = {
  text: string;
  sub?: boolean;
  sup?: boolean;
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  charge?: boolean;
  condition?: boolean;
  isotope?: { mass: string | number; atomic: string | number };
};
export type RichText = string | Run[] | null;

const elements =
  "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split(
    " ",
  );
const atom = `(?:${elements.sort((a, b) => b.length - a.length).join("|")})\\d*`;
const formula = new RegExp(`^(?:${atom}|\\((?:${atom})+\\)\\d*)+$`);
function normalizeSubscriptMarkers(value: string | Run[]): string | Run[] {
  const runs = typeof value === "string" ? [{ text: value }] : value;
  const text = runs.map((run) => run.text).join("");
  const removed = new Set<number>();
  const pattern =
    /(?<![A-Za-z0-9_])\d*([A-Z][A-Za-z0-9()]*(?:_(?:\{\d+\}|\d+)[A-Za-z0-9()]*)+)(?=$|[^A-Za-z0-9_{}]|_{2,})/g;
  for (const match of text.matchAll(pattern)) {
    const body = match[1];
    const markers = /_(?:\{(\d+)\}|(\d+))/g;
    const plain = body.replace(
      markers,
      (_, braced: string, digits: string) => braced || digits,
    );
    if (!formula.test(plain)) continue;
    const start = match.index! + match[0].length - body.length;
    for (const marker of body.matchAll(markers)) {
      for (
        let index = marker.index!;
        index < marker.index! + marker[0].length;
        index++
      ) {
        if ("_{}".includes(body[index])) removed.add(start + index);
      }
    }
  }
  if (!removed.size) return value;
  let offset = 0;
  const result: Run[] = [];
  for (const run of runs) {
    // Offsets use UTF-16 code units, matching RegExp match indices.
    const fragment = run.text
      .split("")
      .filter((_, index) => !removed.has(offset + index))
      .join("");
    offset += run.text.length;
    if (fragment) result.push({ ...run, text: fragment });
  }
  return typeof value === "string"
    ? result.map((run) => run.text).join("")
    : result;
}
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
  /[=═→⟶]*[ \t]*(?:[（(]((?:MnO2|二氧化锰|催化剂)(?:[ ,，、/]*(?:△|Δ|加热))?)[)）]|(MnO2[,，、/]*(?:△|Δ|加热))|(点燃|通电|高温|加热|光照|催化剂|△|Δ))[ \t]*[=═→⟶]*/g;

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
  text
    .replace(/\[([^\[\]]+)\]/g, (all, body: string) =>
      /[=→⟶⇌↔]/.test(body) && hasFormula(body) ? body : all,
    )
    .replace(
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
  if (typeof value === "string" || Array.isArray(value))
    value = normalizeSubscriptMarkers(value);
  if (typeof value === "string") return legacyRuns(value);
  if (!Array.isArray(value)) return value;
  value = joinSemanticConditionLines(value);
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

function equationSide(value: string): boolean {
  return value
    .trim()
    .split("+")
    .every((term) => {
      term = term.replace(/[\s↑↓]/g, "").replace(/^\d+/, "");
      if (term.startsWith("[") && term.endsWith("]")) term = term.slice(1, -1);
      return formula.test(term);
    });
}
function joinSemanticConditionLines(input: Run[]): Run[] {
  const value = input.map((run) => ({ ...run }));
  for (let i = 1; i < value.length - 1; i++) {
    const left = value[i - 1],
      condition = value[i],
      right = value[i + 1];
    if (!condition.condition) continue;
    const end = left.text.match(/[ \t]*\r?\n[ \t]*$/);
    const start = right.text.match(/^[ \t]*\r?\n[ \t]*(?:=+|→|⟶)?[ \t]*/);
    if (!end || !start) continue;
    const lhs = left.text.slice(0, end.index).split("\n").at(-1)!;
    const rhs = right.text.slice(start[0].length).split("\n")[0];
    if (equationSide(lhs) && equationSide(rhs)) {
      left.text = left.text.slice(0, end.index) + " ";
      right.text = " " + right.text.slice(start[0].length);
    }
  }
  return value;
}

function joinEquationLines(runs: Run[]): Run[] {
  const text = runs.map((r) => r.text).join("");
  const side = (value: string) =>
    value
      .trim()
      .split("+")
      .every((term) => {
        term = term.replace(/[\s↑↓]/g, "").replace(/^\d+/, "");
        if (term.startsWith("[") && term.endsWith("]"))
          term = term.slice(1, -1);
        return formula.test(term);
      });
  const edits: { start: number; end: number; text: string }[] = [];
  for (const m of text.matchAll(
    /^([^\r\n]+?)([ \t]*\r?\n[ \t]*)(高温|加热|点燃|通电|光照|△|Δ|催化剂)([ \t]*\r?\n[ \t]*(?:=+|→|⟶)[ \t]*)([^\r\n]+)(?=\r?$)/gm,
  )) {
    if (!side(m[1]) || !side(m[5])) continue;
    const start = m.index! + m[1].length;
    edits.push({ start, end: start + m[2].length, text: " ===" });
    const second = start + m[2].length + m[3].length;
    edits.push({ start: second, end: second + m[4].length, text: "=== " });
  }
  if (!edits.length) return runs;
  let offset = 0;
  const spans = runs.map((run) => {
    const start = offset;
    offset += run.text.length;
    return { start, end: offset, run };
  });
  const result: Run[] = [];
  const keep = (start: number, end: number) => {
    for (const span of spans) {
      const lo = Math.max(start, span.start),
        hi = Math.min(end, span.end);
      if (lo < hi) result.push({ ...span.run, text: text.slice(lo, hi) });
    }
  };
  let position = 0;
  for (const edit of edits) {
    keep(position, edit.start);
    const style = spans.find(
      (s) => s.start <= edit.start && edit.start < s.end,
    )!.run;
    result.push({ ...style, text: edit.text });
    position = edit.end;
  }
  keep(position, text.length);
  return result;
}

function styledGroup(input: Run[]): Run[] {
  const runs = joinEquationLines(
    input.map((r) => ({
      ...r,
      text: coefficient(r.text.replace(/<br\s*\/?>/gi, "\n")),
    })),
  );
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
      conditionMatches.length > 0 || (/[=═→⟶]/.test(line) && hasFormula(line));
    if (equation) {
      lines.push([offset, offset + line.length]);
      for (const m of conditionMatches)
        matches.push({
          start: offset + m.index!,
          end: offset + m.index! + m[0].length,
          labelStart: offset + m.index! + m[0].indexOf(m[1] || m[2] || m[3]),
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
        text: inside ? fragment : markChemicalFormulas(fragment),
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

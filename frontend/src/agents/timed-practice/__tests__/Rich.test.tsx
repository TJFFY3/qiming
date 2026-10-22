// @vitest-environment jsdom
import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import Rich from "../components/Rich";

test.each([
  "[Fe]+[CuSO_4]===[Cu]+[FeSO_4]",
  "Fe+CuSO_{4}===Cu+FeSO_4",
  [
    { text: "Fe+CuSO_", bold: true },
    { text: "4", sub: true },
    { text: "===Cu+FeSO_" },
    { text: "4", sub: true },
  ],
])(
  "removes chemical subscript syntax in current and historical previews",
  (value) => {
    const { container } = render(<Rich value={value} />);
    expect(container.textContent).toBe("Fe+CuSO4===Cu+FeSO4");
    expect(
      Array.from(container.querySelectorAll("sub"), (node) => node.textContent),
    ).toEqual(["4", "4"]);
  },
);

test("keeps answer blanks and ordinary identifiers while cleaning chemical subscripts", () => {
  const { container } = render(
    <Rich value="填空______；x_1、sample_2、ABC_3；[CO_2]______" />,
  );
  expect(container.textContent).toBe(
    "填空______；x_1、sample_2、ABC_3；CO2______",
  );
  expect(container.querySelector("sub")?.textContent).toBe("2");
});

test("practice preview preserves equation lines and scripts in catalyst conditions", () => {
  const { container } = render(
    <Rich
      value={[
        { text: "①CO" },
        { text: "2", sub: true },
        { text: "+C" },
        { text: "高温", condition: true },
        { text: "2CO\n②2KClO" },
        { text: "3", sub: true },
        { text: "MnO2、△", condition: true },
        { text: "2KCl+3O" },
        { text: "2", sub: true },
        { text: "↑" },
      ]}
    />,
  );
  expect(container.querySelectorAll("br")).toHaveLength(1);
  const conditions = container.querySelectorAll(".tp-condition");
  expect(conditions).toHaveLength(2);
  expect(conditions[1].querySelector("small sub")?.textContent).toBe("2");
  expect(conditions[1].textContent).toContain("MnO2、△");
});

test.each([
  ["2CO+O2点燃2CO2", "点燃", ["2", "2"]],
  ["Na2O+H2O═2NaOH", undefined, ["2", "2"]],
  ["2H2O通电2H2↑+O2↑", "通电", ["2", "2", "2"]],
  ["CH4+2O2点燃CO2+2H2O", "点燃", ["4", "2", "2", "2"]],
  ["2KClO3(MnO2,△)2KCl+3O2↑", "MnO2、△", ["3", "2", "2"]],
] as const)("normalizes screenshot equation: %s", (value, condition, subs) => {
  const { container } = render(<Rich value={value} />);
  expect(
    Array.from(container.querySelectorAll("sub"), (node) => node.textContent),
  ).toEqual(subs);
  if (condition)
    expect(container.querySelector(".tp-condition small")?.textContent).toBe(
      condition,
    );
  expect(container.textContent).not.toContain("(MnO2,△)");
});

test("formats equations without conditions on every line of a question", () => {
  const { container } = render(
    <Rich value={"①CO2+C高温2CO\n⑤2FeCl3+Cu=2FeCl2+CuCl2"} />,
  );
  expect(
    Array.from(container.querySelectorAll("sub"), (node) => node.textContent),
  ).toEqual(["2", "3", "2", "2"]);
  expect(container.querySelector(".tp-condition small")?.textContent).toBe(
    "高温",
  );
  expect(container.querySelector("br")).not.toBeNull();
});

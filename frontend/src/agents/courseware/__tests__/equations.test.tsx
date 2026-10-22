// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { Rich } from "../components/Preview";

afterEach(cleanup);

test.each([
  "[2CuO+C=高温=2Cu+CO2↑]",
  "[Fe2O3+3CO=高温=2Fe+3CO2]",
  "[2CuO]+[C]=高温=[2Cu]+[CO2]↑",
])("coefficients stay on the baseline in %s", (value) => {
  const { container } = render(<Rich value={value} />);
  const subs = [...container.querySelectorAll("sub")].map((s) => s.textContent);
  expect(subs).toEqual(value.includes("Fe") ? ["2", "3", "2"] : ["2"]);
  expect(container.textContent).not.toMatch(/[\[\]]/);
  expect(container.querySelector(".cw-condition small")?.textContent).toBe(
    "高温",
  );
});

test("styled semantic runs retain coefficients, atom counts and ionic charges", () => {
  const { container } = render(
    <Rich
      value={[
        { text: "2[CuO]+[C]", bold: true },
        { text: "高温", condition: true },
        { text: "2[Cu]+[CO2]↑" },
        { text: "；[Fe^3+]、[SO4^2-]；第2组" },
      ]}
    />,
  );
  expect(
    [...container.querySelectorAll("sub")].map((s) => s.textContent),
  ).toEqual(["2", "4"]);
  expect(
    [...container.querySelectorAll("sup")].map((s) => s.textContent),
  ).toEqual(["3+", "2-"]);
  expect(container.textContent).toContain("第2组");
});

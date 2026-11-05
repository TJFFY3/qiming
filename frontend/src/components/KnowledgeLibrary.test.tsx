// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import KnowledgeLibrary from "./KnowledgeLibrary";
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

test("nine subject tabs keep their order and show only the selected subject", async () => {
  const fetcher=vi.fn(async () => Response.json({synced_at:"2026-11-05",chunk_count:0,documents:[
    {id:"chem",dataset_id:"chem-db",subject:"化学",dataset_name:"化学教材库",title:"化学教材.pdf",kind:"document",chunks:[]},
    {id:"math",dataset_id:"math-db",subject:"数学",dataset_name:"数学教材库",title:"数学教材.pdf",kind:"document",chunks:[]}
  ]}));
  vi.stubGlobal("fetch",fetcher);
  render(<KnowledgeLibrary />);
  await screen.findByRole("button",{name:/化学教材.pdf/});
  const tabs=screen.getByRole("tablist",{name:"知识库学科"});
  const order=["语文","数学","英语","物理","化学","生物","政治","历史","地理"];
  expect(within(tabs).getAllByRole("tab").map(el=>el.textContent)).toEqual(order);
  expect(screen.queryByRole("button",{name:/数学教材.pdf/})).toBeNull();
  fireEvent.click(within(tabs).getByRole("tab",{name:"数学"}));
  expect(screen.getByRole("button",{name:/数学教材.pdf/})).toBeTruthy();
  expect(screen.queryByRole("button",{name:/化学教材.pdf/})).toBeNull();
  expect(within(tabs).getAllByRole("tab").map(el=>el.textContent)).toEqual(order);
  expect(fetcher).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(within(tabs).getByRole("tab",{name:"数学"}),{key:"ArrowRight"});
  expect(within(tabs).getByRole("tab",{name:"英语"}).getAttribute("aria-selected")).toBe("true");
  expect(screen.getByText("英语暂无知识库资料。")).toBeTruthy();
});

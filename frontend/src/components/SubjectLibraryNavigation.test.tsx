// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import App from "../App";

afterEach(() => {cleanup();localStorage.clear();vi.unstubAllGlobals();window.history.replaceState(null,"","#guide");});

test.each([
  {id:"guide",subject:"学科",chapter:"章节 / 知识点"},
  {id:"courseware",subject:"课件学科",chapter:"课件章节"},
  {id:"practice",subject:"限时练习学科",chapter:"限时练习章节"},
])("$id selection reveals and locates the matching knowledge file", async agent => {
  window.history.replaceState(null,"","#"+agent.id);
  const fetcher=vi.fn(async (input: RequestInfo | URL) => {
    const url=String(input);
    if (url.endsWith("/health")) return Response.json({ready:true,missing:[]});
    if (url.endsWith("/library/subjects")) return Response.json({subjects:["化学","数学"]});
    if (url.includes("/library/chapters")) return Response.json({chapters:url.includes(encodeURIComponent("数学")) ? ["第一章 集合","第二章 函数"] : ["第一章 物质及其变化"]});
    if (url.endsWith("/library")) return Response.json({synced_at:"2026-11-05",chunk_count:0,documents:[
      {id:"m1",dataset_id:"math",subject:"数学",dataset_name:"数学教材库",title:"数学 第一章 集合.pdf",kind:"document",chunks:[]},
      {id:"m2",dataset_id:"math",subject:"数学",dataset_name:"数学教材库",title:"数学 第二章 函数.pdf",kind:"document",chunks:[]},
      {id:"c1",dataset_id:"chem",subject:"化学",dataset_name:"化学教材库",title:"化学 第一章 物质及其变化.pdf",kind:"document",chunks:[]},
    ]});
    return Response.json({});
  });
  vi.stubGlobal("fetch",fetcher);
  render(<App />);await act(async()=>{});
  fireEvent.click(screen.getByRole("button",{name:"隐藏文件预览"}));
  fireEvent.change(screen.getByRole("combobox",{name:agent.subject}),{target:{value:"数学"}});
  const library=await screen.findByRole("dialog",{name:"资料库"});
  expect(library.closest(".workbench-preview")).toBeTruthy();
  expect(within(library).queryByRole("heading",{name:"资料库"})).toBeNull();
  expect(within(library).queryByRole("button",{name:"关闭"})).toBeNull();
  expect(library.querySelector(".modal-header")).toBeNull();
  expect(document.querySelector(".agent-workbench")?.getAttribute("data-preview")).toBe("true");
  expect(within(library).getByRole("tab",{name:"数学"}).getAttribute("aria-selected")).toBe("true");
  await screen.findByRole("option",{name:"第二章 函数"});
  await within(library).findByRole("button",{name:/数学 第二章 函数.pdf/});
  await waitFor(() => expect(within(library).getByRole("button",{name:/数学 第一章 集合.pdf/}).getAttribute("aria-expanded")).toBe("true"));
  fireEvent.change(within(library).getByRole("textbox",{name:"筛选知识库资料"}),{target:{value:"无匹配"}});
  fireEvent.change(screen.getByRole("combobox",{name:agent.chapter}),{target:{value:"第二章 函数"}});
  const file=await within(library).findByRole("button",{name:/数学 第二章 函数.pdf/});
  expect(file.getAttribute("aria-expanded")).toBe("true");
  expect(file.closest(".library-document-focused")).toBeTruthy();
  expect(within(library).getByRole("textbox",{name:"筛选知识库资料"}).getAttribute("value")).toBe("");
  expect(fetcher.mock.calls.some(([url])=>String(url).endsWith("/generate"))).toBe(false);
});

test.each(["close","history"])("late chapter results do not reopen the library after %s", async action => {
  let resolveChapters!: (response: Response) => void;
  const pending=new Promise<Response>(resolve=>{resolveChapters=resolve;});
  vi.stubGlobal("fetch",vi.fn(async (input:RequestInfo|URL)=>{
    const url=String(input);
    if (url.includes("/library/chapters")) return url.includes(encodeURIComponent("数学")) ? pending : Response.json({chapters:["化学课题"]});
    if (url.endsWith("/library/subjects")) return Response.json({subjects:["化学","数学"]});
    if (url.endsWith("/library")) return Response.json({synced_at:"2026-11-05",chunk_count:0,documents:[]});
    if (url.endsWith("/sessions")) return Response.json([]);
    return Response.json({ready:true,missing:[]});
  }));
  render(<App />);await act(async()=>{});
  fireEvent.change(screen.getByRole("combobox",{name:"学科"}),{target:{value:"数学"}});
  await screen.findByRole("dialog",{name:"资料库"});
  if (action === "close") fireEvent.click(screen.getByRole("button",{name:"完成"}));
  else {
    fireEvent.click(screen.getByRole("button",{name:"历史备课"}));
    await screen.findByRole("dialog",{name:"历史备课"});
  }
  await act(async()=>{resolveChapters(Response.json({chapters:["第二章 函数"]}));await pending;});
  await screen.findByRole("option",{name:"第二章 函数"});
  expect(screen.queryByRole("dialog",{name:"资料库"})).toBeNull();
  if (action === "history") expect(screen.getByRole("dialog",{name:"历史备课"})).toBeTruthy();
});

test.each([
  {id:"guide",chapter:"章节 / 知识点"},
  {id:"courseware",chapter:"课件章节"},
  {id:"practice",chapter:"限时练习章节"},
])("$id chapter choices follow a successful knowledge library sync", async agent => {
  window.history.replaceState(null,"","#"+agent.id);
  let synced=false;
  const catalog=() => ({synced_at:synced ? "new" : "old",chunk_count:0,documents:[{
    id:"chem",dataset_id:"chem-db",subject:"化学",dataset_name:"化学教材库",kind:"document",chunks:[],
    title:synced ? "化学 第二章 钠和氯.pdf" : "化学 第一章 物质及其变化.pdf",
  }]});
  vi.stubGlobal("fetch",vi.fn(async (input:RequestInfo|URL) => {
    const url=String(input);
    if (url.includes("/library/chapters")) return Response.json({chapters:[synced ? "第二章 钠和氯" : "第一章 物质及其变化"]});
    if (url.endsWith("/library/subjects")) return Response.json({subjects:["化学"]});
    if (url.endsWith("/library/sync")) {synced=true;return Response.json(catalog());}
    if (url.endsWith("/library")) return Response.json(catalog());
    return Response.json({ready:true,missing:[]});
  }));
  render(<App />);
  await waitFor(() => expect((screen.getByRole("combobox",{name:agent.chapter}) as HTMLSelectElement).value).toBe("第一章 物质及其变化"));
  fireEvent.click(screen.getByRole("button",{name:"资料库"}));
  const library=await screen.findByRole("dialog",{name:"资料库"});
  fireEvent.click(await within(library).findByRole("button",{name:"同步知识库"}));
  await within(library).findByRole("button",{name:/化学 第二章 钠和氯.pdf/});
  await waitFor(() => expect((screen.getByRole("combobox",{name:agent.chapter}) as HTMLSelectElement).value).toBe("第二章 钠和氯"));
  expect(screen.queryByRole("option",{name:"第一章 物质及其变化"})).toBeNull();
});

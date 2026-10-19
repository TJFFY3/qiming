// @vitest-environment jsdom
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import SourceEvidence from "./SourceEvidence";
vi.mock("../metafile", () => ({
  convertSourceImage: vi.fn(async () => "data:image/png;base64,converted"),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
test("renders FastGPT Markdown images inline and retains original URL", () => {
  render(
    <SourceEvidence
      text={
        "原文说明\n\n![实验装置](https://cloud.fastgpt.cn/api/system/file/d/example)\n\n后续说明"
      }
    />,
  );
  expect(
    screen.getByRole("img", { name: "实验装置" }).getAttribute("src"),
  ).toBe("https://cloud.fastgpt.cn/api/system/file/d/example");
  expect(
    screen.getByRole("link", { name: "查看原图" }).getAttribute("href"),
  ).toBe("https://cloud.fastgpt.cn/api/system/file/d/example");
  expect(screen.getByText("后续说明")).toBeTruthy();
});
test("converts unsupported Office image formats after native image failure", async () => {
  render(
    <SourceEvidence
      text={
        "![反应条件](https://cloud.fastgpt.cn/api/system/file/d/office-image)"
      }
    />,
  );
  fireEvent.error(screen.getByRole("img", { name: "反应条件" }));
  await waitFor(() =>
    expect(
      screen.getByRole("img", { name: "反应条件" }).getAttribute("src"),
    ).toBe("data:image/png;base64,converted"),
  );
});
test("failed image conversion retains a useful error and original link", async () => {
  const { convertSourceImage } = await import("../metafile");
  vi.mocked(convertSourceImage).mockRejectedValueOnce(new Error("bad"));
  render(
    <SourceEvidence
      text={"![装置图](https://cloud.fastgpt.cn/api/system/file/d/fail)"}
    />,
  );
  fireEvent.error(screen.getByRole("img", { name: "装置图" }));
  await waitFor(() =>
    expect(screen.getByText("图片暂时无法显示")).toBeTruthy(),
  );
  expect(screen.getByRole("link", { name: "查看原图" })).toBeTruthy();
});
test("does not execute raw HTML or allow executable image URLs", () => {
  const { container } = render(
    <SourceEvidence
      text={
        "<script>alert(1)</script>\n\n![bad](javascript:alert%281%29)\n\n<img src=x onerror=alert(1) />"
      }
    />,
  );
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("img")).toBeNull();
});

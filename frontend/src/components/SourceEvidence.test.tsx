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
test("loads stable same-origin images and preserves Office conversion fallback", async () => {
  const url = "/api/library/images/aaaaaaaaaaaaaaaaaaaaaaaa/0?v=0123456789abcdef";
  const { convertSourceImage } = await import("../metafile");
  render(<SourceEvidence text={`![装置图](${url})`} />);
  expect(screen.getByRole("img", { name: "装置图" }).getAttribute("src")).toBe(url);
  expect(screen.getByRole("link", { name: "查看原图" }).getAttribute("href")).toBe(url);
  fireEvent.error(screen.getByRole("img", { name: "装置图" }));
  await waitFor(() => expect(screen.getByRole("img", { name: "装置图" }).getAttribute("src")).toBe("data:image/png;base64,converted"));
  expect(convertSourceImage).toHaveBeenCalledWith(url);
});
test("refreshing the catalog remounts an Office image for the new snapshot", async () => {
  const before = "/api/library/images/aaaaaaaaaaaaaaaaaaaaaaaa/0?v=0123456789abcdef";
  const after = "/api/library/images/aaaaaaaaaaaaaaaaaaaaaaaa/0?v=fedcba9876543210";
  const { rerender } = render(<SourceEvidence text={`![装置图](${before})`} />);
  fireEvent.error(screen.getByRole("img", { name: "装置图" }));
  await waitFor(() => expect(screen.getByRole("img", { name: "装置图" }).getAttribute("src")).toBe("data:image/png;base64,converted"));
  rerender(<SourceEvidence text={`![装置图](${after})`} />);
  expect(screen.getByRole("img", { name: "装置图" }).getAttribute("src")).toBe(after);
});
test("rejects arbitrary relative and protocol-relative image URLs", () => {
  const { container } = render(<SourceEvidence text={"![bad](/api/sessions)\n\n![bad](//evil.test/image)"} />);
  expect(container.querySelector("img")).toBeNull();
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

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "../../i18n";
import { fakeSources } from "../../project/fake";
import { workspaceApi } from "../api";
import { ProjectMapDoc } from "./ProjectMapDoc";
const status = {
  waiting: 0,
  reading: 0,
  done: 1,
  failed: 0,
  total: 1,
  line: { en: "Reading 1 of 1 files", ar: "بنقرا ملف ١ من ١" },
};
const file = {
  file_id: "f1",
  name: "sample.pdf",
  pages: 58,
  read_how: "ocr",
  ai_title: { en: "Sample contract", ar: "عقد عينة" },
  key_pages: [{
    label: { en: "Contract data", ar: "بيانات العقد" },
    page: 58,
    box: [1, 2, 3, 4],
  }],
};
let facts: unknown[];
let calls: string[];
beforeEach(() => {
  setLanguage("en");
  facts = [];
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push(url);
      if (init?.method === "POST") {
        facts = [{
          ...(facts[0] as object),
          confirmed_by: "engineer",
          corrected_value: JSON.parse(init.body as string).value ?? null,
        }];
        return Response.json({});
      }
      if (url.includes("/facts")) {
        return Response.json({ facts, next_cursor: null });
      }
      if (url.includes("/links")) {
        return Response.json({ links: [], next_cursor: null });
      }
      return Response.json({
        status,
        groups: [],
        files: [file],
        next_cursor: null,
      });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());
function show() {
  return render(<ProjectMapDoc projectId="p" sources={fakeSources({})} />);
}
it("shows one OCR file and opens its marked key page", async () => {
  const open = vi.spyOn(workspaceApi, "open").mockImplementation(() => {});
  show();
  expect(await screen.findByText("sample.pdf")).toBeInTheDocument();
  expect(screen.getByText(/· OCR/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: /Contract data/ }));
  expect(open).toHaveBeenCalledWith("file:f1", { page: 58, box: [1, 2, 3, 4] });
  open.mockRestore();
});
it("shows an empty project and Arabic RTL", async () => {
  setLanguage("ar");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        url.includes("/facts")
          ? { facts: [], next_cursor: null }
          : url.includes("/links")
          ? { links: [], next_cursor: null }
          : {
            status: { ...status, total: 0 },
            groups: [],
            files: [],
            next_cursor: null,
          },
      )
    ),
  );
  show();
  expect(await screen.findByText("لسه مفيش ملفات في المشروع."))
    .toBeInTheDocument();
  expect(screen.getByRole("region")).toHaveAttribute("dir", "rtl");
});
it("confirms and corrects in place, retaining the replaced value", async () => {
  facts = [{
    id: "fact",
    name: { en: "Currency", ar: "العملة" },
    value: "EGP",
    file_id: "f1",
    locator: { page: 1 },
    state: "found",
    conflict_with: [],
  }];
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));
  await screen.findByText("Confirmed");
  const input = screen.getByRole("textbox", { name: "Currency" });
  fireEvent.change(input, { target: { value: "SAR" } });
  fireEvent.blur(input);
  await waitFor(() =>
    expect(document.querySelector("del")).toHaveTextContent("EGP")
  );
});
it("loads bounded pages on demand and keeps 10,000 files virtualised", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes("/facts")) {
        return Response.json({ facts: [], next_cursor: null });
      }
      if (url.includes("/links")) {
        return Response.json({ links: [], next_cursor: null });
      }
      const offset = url.includes("cursor=") ? 100 : 0;
      return Response.json({
        status: { ...status, total: 10000 },
        groups: [],
        files: Array.from(
          { length: 100 },
          (_, i) => ({
            ...file,
            file_id: `f${offset + i}`,
            name: `sample-${offset + i}.pdf`,
          }),
        ),
        next_cursor: offset ? null : "next",
      });
    }),
  );
  show();
  await screen.findByText("sample-0.pdf");
  expect(document.querySelectorAll("[data-map-file]").length).toBeLessThan(40);
  expect(calls.filter((x) => x.includes("/map?")).length).toBe(1);
  fireEvent.scroll(document.querySelector("[data-map-scroll]")!, {
    target: { scrollTop: 6500 },
  });
  fireEvent.click(await screen.findByRole("button", { name: "More files" }));
  await waitFor(() =>
    expect(calls.some((x) => x.includes("cursor=next"))).toBe(true)
  );
  expect(document.querySelectorAll("[data-map-file]").length).toBeLessThan(40);
});
it("opens folders lazily without repeating the flat root file list", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      calls.push(url);
      if (url.includes("/facts")) {
        return Response.json({ facts: [], next_cursor: null });
      }
      if (url.includes("/links")) {
        return Response.json({ links: [], next_cursor: null });
      }
      return Response.json({
        status: { ...status, total: 2 },
        groups: url.includes("parent=") ? [] : [{
          path: "Contract",
          label: { en: "Contract", ar: "العقد" },
          count: 1,
        }],
        files: [file],
        next_cursor: null,
      });
    }),
  );
  show();
  const group = await screen.findByRole("button", { name: /▸ Contract/ });
  expect(screen.queryByText("sample.pdf")).toBeNull();
  expect(calls.some((x) => x.includes("parent="))).toBe(false);
  fireEvent.click(group);
  await screen.findByText("sample.pdf");
  expect(calls.some((x) => x.includes("parent=Contract"))).toBe(true);
});
it("shows both conflicting sources and writes the engineer's choice", async () => {
  facts = [{
    id: "fact",
    name: { en: "Currency", ar: "العملة" },
    value: "EGP",
    file_id: "f1",
    locator: { page: 1 },
    state: "conflict",
    conflict_with: [{ value: "SAR", file_id: "f2", locator: { page: 2 } }],
  }];
  show();
  await screen.findByText("Conflict — choose a value");
  expect(screen.getByRole("button", { name: /Page 1$/ })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Page 2$/ })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Use this value" }));
  await waitFor(() =>
    expect(screen.getByRole("textbox", { name: "Currency" })).toHaveValue("SAR")
  );
  expect(document.querySelector("del")).toHaveTextContent("EGP");
});
it("opens linked pages side by side in the existing file viewer", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        url.includes("/facts")
          ? { facts: [], next_cursor: null }
          : url.includes("/links")
          ? {
            links: [{
              id: "link",
              from_file_id: "f1",
              from_locator: { page: 1 },
              to_file_id: "f2",
              to_locator: { page: 2 },
              words: {
                en: "Sample addendum changes clause",
                ar: "ملحق عينة بيغيّر البند",
              },
            }],
            next_cursor: null,
          }
          : { status, groups: [], files: [file], next_cursor: null },
      )
    ),
  );
  render(
    <ProjectMapDoc
      projectId="p"
      sources={fakeSources({ pages: { f1: 2, f2: 2 } })}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", {
      name: "Sample addendum changes clause",
    }),
  );
  await waitFor(() => expect(screen.getAllByRole("img")).toHaveLength(2));
  expect(screen.getAllByRole("img")[0]).toHaveAttribute(
    "src",
    expect.stringContaining("f1/1/"),
  );
  expect(screen.getAllByRole("img")[1]).toHaveAttribute(
    "src",
    expect.stringContaining("f2/2/"),
  );
});
it("polls the real status and refreshes file metadata", async () => {
  show();
  await screen.findByText("sample.pdf");
  file.ai_title = { en: "Updated sample", ar: "عينة محدثة" };
  await screen.findByText("Updated sample", {}, { timeout: 3500 });
});
it("keeps a one-file project to one line even when the API supplies a group", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json(
        url.includes("/facts")
          ? { facts: [], next_cursor: null }
          : url.includes("/links")
          ? { links: [], next_cursor: null }
          : {
            status,
            groups: [{
              path: "pdf",
              label: { en: "pdf", ar: "pdf" },
              count: 1,
            }],
            files: [file],
            next_cursor: null,
          },
      )
    ),
  );
  show();
  expect(await screen.findByText("sample.pdf")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /▸ pdf/ })).toBeNull();
});
it("keeps an unsuccessful confirmation unconfirmed", async () => {
  facts = [{
    id: "fact",
    name: { en: "Currency", ar: "العملة" },
    value: "EGP",
    file_id: "f1",
    locator: { page: 1 },
    state: "found",
    conflict_with: [],
  }];
  const original = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) =>
      init?.method === "POST"
        ? Promise.resolve(new Response("", { status: 500 }))
        : original(url, init)
    ),
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: "Confirm" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText("Confirmed")).toBeNull();
});
it("opens a key sheet at its one-based source row", async () => {
  const open = vi.spyOn(workspaceApi, "open").mockImplementation(() => {});
  const original = globalThis.fetch;
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) =>
      url.includes("/facts") || url.includes("/links")
        ? original(url, init)
        : Promise.resolve(
          Response.json({
            status,
            groups: [],
            files: [{
              ...file,
              key_pages: [{
                label: { en: "Sample total", ar: "إجمالي عينة" },
                sheet: "BOQ",
                row: 14,
              }],
            }],
            next_cursor: null,
          }),
        )
    ),
  );
  show();
  fireEvent.click(await screen.findByRole("button", { name: /Sample total/ }));
  expect(open).toHaveBeenCalledWith("file:f1", { sheet: "BOQ", row: "r14" });
  open.mockRestore();
});

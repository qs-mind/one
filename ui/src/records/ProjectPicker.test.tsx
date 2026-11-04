import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../chat/Chat";
import { setLanguage, texts } from "../i18n";
import { currentProject, setCurrentProject } from "./project";

// Sample projects, as the core lists them.
const school = { id: "a".repeat(32), name: "مدرسة - عينة", created_at: "2026-11-04T08:00:00.000000+00:00" };
const tower = { id: "b".repeat(32), name: "Tower - sample", created_at: "2026-11-03T08:00:00.000000+00:00" };
const damaged = { en: "This project file cannot be read.", ar: "ملف هذا المشروع لا يمكن قراءته." };

type Route = (init: RequestInit) => Response | Promise<Response>;

// The core behind /api: the routes a test gives, plus the settings the header always asks for.
function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const route = routes[`${init.method ?? "GET"} ${url}`];
    if (route) return route(init);
    if (url === "/api/settings/ai-key") return Response.json({ set: true });
    if (url === "/api/settings/model") return Response.json({ id: "claude-opus-5-5" });
    if (url === "/api/settings/models") return Response.json([]);
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const picker = () => screen.getByRole("region", { name: texts.projects.ar });
const called = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls.filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method);

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("ProjectPicker", () => {
  it("lists projects, opens one and shows its name in the header", async () => {
    const fetch = core({
      "GET /api/projects": () =>
        Response.json({
          projects: [
            { ...school, open: false },
            { ...tower, open: false },
            { id: "c".repeat(32), error: damaged },
          ],
        }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }),
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.projects.ar }));

    expect(await within(picker()).findByRole("button", { name: tower.name })).toBeInTheDocument();
    expect(within(picker()).getByText(damaged.ar)).toBeInTheDocument(); // listed with its reason, not hidden
    await user.click(within(picker()).getByRole("button", { name: school.name }));

    expect(await screen.findByRole("button", { name: school.name })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: texts.projects.ar })).not.toBeInTheDocument();
    expect(called(fetch, "POST", `/api/projects/${school.id}/open`)).toHaveLength(1);
    expect(currentProject()?.id).toBe(school.id);
    expect(localStorage.getItem("qsone.project")).toBe(school.id);
  });

  it("opening another project closes the one before it in the core", async () => {
    setCurrentProject(tower);
    const fetch = core({
      "GET /api/projects": () =>
        Response.json({
          projects: [
            { ...school, open: false },
            { ...tower, open: true },
          ],
        }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }),
      [`POST /api/projects/${tower.id}/close`]: () => Response.json({ open: false }),
      [`POST /api/projects/${tower.id}/open`]: () => Response.json({ ...tower, open: true }), // remembered on start
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: tower.name }));
    const current = await within(picker()).findByRole("button", { name: new RegExp(tower.name) });
    expect(current).toHaveAttribute("aria-current", "true");
    expect(current).toHaveTextContent(texts.open.ar);

    await user.click(within(picker()).getByRole("button", { name: school.name }));
    await waitFor(() => expect(called(fetch, "POST", `/api/projects/${tower.id}/close`)).toHaveLength(1));
  });

  it("creates a project from a name", async () => {
    const fetch = core({
      "GET /api/projects": () => Response.json({ projects: [] }),
      "POST /api/projects": () => Response.json({ ...school, open: true }, { status: 201 }),
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.projects.ar }));
    expect(await within(picker()).findByText(texts.noProjects.ar)).toBeInTheDocument();

    const name = within(picker()).getByLabelText(texts.projectName.ar);
    expect(name).toHaveAttribute("dir", "auto");
    await user.type(name, "  مدرسة - عينة ");
    await user.click(within(picker()).getByRole("button", { name: texts.create.ar }));

    expect(await screen.findByRole("button", { name: school.name })).toBeInTheDocument();
    const [, init] = called(fetch, "POST", "/api/projects")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ name: "مدرسة - عينة" });
    expect(currentProject()?.id).toBe(school.id);
  });

  it("a project that does not open keeps the picker with the core's plain reason", async () => {
    const missing = {
      en: "The project's key is not in the key store.",
      ar: "مفتاح المشروع غير موجود في مخزن المفاتيح.",
    };
    core({
      "GET /api/projects": () => Response.json({ projects: [{ ...school, open: false }] }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ error: missing }, { status: 409 }),
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.projects.ar }));
    await user.click(await within(picker()).findByRole("button", { name: school.name }));

    expect(await within(picker()).findByRole("alert")).toHaveTextContent(missing.ar);
    expect(currentProject()).toBeUndefined();
  });

  it("a remembered project opens on start", async () => {
    localStorage.setItem("qsone.project", school.id);
    core({ [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }) });
    render(<Chat />);
    expect(await screen.findByRole("button", { name: school.name })).toBeInTheDocument();
  });

  it("a remembered project that cannot open is forgotten, and the picker shows", async () => {
    localStorage.setItem("qsone.project", school.id);
    core({
      "GET /api/projects": () => Response.json({ projects: [] }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ error: damaged }, { status: 409 }),
    });
    render(<Chat />);
    expect(await screen.findByRole("region", { name: texts.projects.ar })).toBeInTheDocument();
    expect(localStorage.getItem("qsone.project")).toBeNull();
    expect(screen.getByRole("button", { name: texts.projects.ar })).toBeInTheDocument();
  });

  it("works from the keyboard", async () => {
    core({
      "GET /api/projects": () => Response.json({ projects: [{ ...school, open: false }] }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }),
    });
    const user = userEvent.setup();
    render(<Chat />);
    await user.tab();
    expect(screen.getByRole("button", { name: texts.projects.ar })).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(within(picker()).getByRole("button", { name: school.name })).toHaveFocus());
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("button", { name: school.name })).toBeInTheDocument();
  });

  it("shows its labels in English too", async () => {
    setLanguage("en");
    core({ "GET /api/projects": () => Response.json({ projects: [] }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.projects.en }));
    const region = screen.getByRole("region", { name: texts.projects.en });
    expect(await within(region).findByText(texts.noProjects.en)).toBeInTheDocument();
    expect(within(region).getByLabelText(texts.projectName.en)).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: texts.create.en })).toBeInTheDocument();
  });
});

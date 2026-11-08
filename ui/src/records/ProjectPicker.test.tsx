import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, t, texts } from "../i18n";
import { App } from "../shell/App";
import { currentProject, setCurrentProject } from "./project";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("../shell/testing")).WorkspaceStandIn, DocumentHead: () => null }));

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
/** The top bar's project button: the project's name, or "General chat" with none open. */
const switcher = (_name: string = texts.generalChat.ar) =>
  within(screen.getByRole("banner")).getByTitle(t("projects"));
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
    render(<App />);
    await user.click(switcher());

    expect(await within(picker()).findByRole("button", { name: tower.name })).toBeInTheDocument();
    expect(within(picker()).getByText(damaged.ar)).toBeInTheDocument(); // listed with its reason, not hidden
    await user.click(within(picker()).getByRole("button", { name: school.name }));

    await waitFor(() => expect(switcher(school.name)).toBeInTheDocument());
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
    render(<App />);
    await waitFor(() => expect(currentProject()?.id).toBe(tower.id));
    await user.click(switcher());
    const current = await within(picker()).findByRole("button", { name: new RegExp(tower.name) });
    expect(current).toHaveAttribute("aria-current", "true");
    expect(current).toHaveTextContent(texts.open.ar);

    await user.click(within(picker()).getByRole("button", { name: school.name }));
    await waitFor(() => expect(called(fetch, "POST", `/api/projects/${tower.id}/close`)).toHaveLength(1));
  });

  it("creates a project from files without a name", async () => {
    const fetch = core({
      "GET /api/projects": () => Response.json({ projects: [] }),
      "POST /api/projects": () => Response.json({ ...school, open: true }, { status: 201 }),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(switcher());
    await user.click(await within(picker()).findByRole("button", { name: texts.newProject.ar }));

    expect(within(picker()).queryByLabelText(texts.projectName.ar)).toBeNull();
    const input = picker().querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["sample"], "sample.txt"));

    await waitFor(() => expect(switcher(school.name)).toBeInTheDocument());
    const [, init] = called(fetch, "POST", "/api/projects")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({});
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
    render(<App />);
    await user.click(switcher());
    await user.click(await within(picker()).findByRole("button", { name: school.name }));

    expect(await within(picker()).findByRole("alert")).toHaveTextContent(missing.ar);
    expect(currentProject()).toBeUndefined();
  });

  it("a remembered project opens on start", async () => {
    localStorage.setItem("qsone.project", school.id);
    core({ [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }) });
    render(<App />);
    await waitFor(() => expect(switcher(school.name)).toBeInTheDocument());
  });

  it("a remembered project is kept while the core is still coming back, and opens once it answers", async () => {
    localStorage.setItem("qsone.project", school.id);
    let tries = 0;
    core({
      [`POST /api/projects/${school.id}/open`]: () =>
        ++tries < 3 ? new Response("starting", { status: 502 }) : Response.json({ ...school, open: true }),
    });
    render(<App />);
    await waitFor(() => expect(switcher(school.name)).toBeInTheDocument(), { timeout: 5000 });
    expect(localStorage.getItem("qsone.project")).toBe(school.id);
    expect(screen.queryByRole("region", { name: texts.projects.ar })).toBeNull();
  });

  it("a remembered project that cannot open is forgotten, and the picker shows", async () => {
    localStorage.setItem("qsone.project", school.id);
    core({
      "GET /api/projects": () => Response.json({ projects: [] }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ error: damaged }, { status: 409 }),
    });
    render(<App />);
    expect(await screen.findByRole("region", { name: texts.projects.ar })).toBeInTheDocument();
    expect(localStorage.getItem("qsone.project")).toBeNull();
    expect(switcher()).toBeInTheDocument();
  });

  it("works from the keyboard", async () => {
    core({
      "GET /api/projects": () => Response.json({ projects: [{ ...school, open: false }] }),
      [`POST /api/projects/${school.id}/open`]: () => Response.json({ ...school, open: true }),
    });
    const user = userEvent.setup();
    render(<App />);
    await user.tab();
    expect(switcher()).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(within(picker()).getByRole("button", { name: school.name })).toHaveFocus());
    await user.keyboard("{Enter}");
    await waitFor(() => expect(switcher(school.name)).toHaveFocus()); // focus back on the top bar's button
  });

  it("shows its labels in English too", async () => {
    setLanguage("en");
    core({ "GET /api/projects": () => Response.json({ projects: [] }) });
    const user = userEvent.setup();
    render(<App />);
    await user.click(switcher(texts.generalChat.en));
    const region = screen.getByRole("region", { name: texts.projects.en });
    await user.click(await within(region).findByRole("button", { name: texts.newProject.en }));
    expect(within(region).getByRole("button", { name: texts.chooseProjectFiles.en })).toBeInTheDocument();
    expect(within(region).getByRole("button", { name: texts.chooseProjectFolder.en })).toBeInTheDocument();
  });
});

import { clearMocks, mockIPC } from "@tauri-apps/api/mocks";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { BackupPanel } from "./BackupPanel";
import { Confidential } from "./Confidential";
import { RecoveryCode } from "./RecoveryCode";
import { Restore } from "./Restore";

type Handler = (body: Record<string, unknown> | undefined, url: string) => Response;

function mockCore(routes: Record<string, Handler>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api/, "");
    const key = `${init.method ?? "GET"} ${url.split("?")[0]}`;
    const body = typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
    return routes[key]?.(body, url) ?? new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const CODE = "K7Q2M-9XWPL-4RT8N-B3VHC-ZD6JF"; // made up for the test, not a real code

const status = (over: Record<string, unknown> = {}) => ({
  folder: null,
  reachable: true,
  last_run: null,
  note: null,
  backup_key: { local: true, in_account: false, code_saved: false },
  projects: [],
  ...over,
});

beforeEach(() => setLanguage("en"));
afterEach(() => {
  clearMocks();
  vi.unstubAllGlobals();
});

describe("the recovery code", () => {
  it("shows once in a box and asks for its last group", async () => {
    const sent: unknown[] = [];
    mockCore({
      "POST /backup/recovery-code/confirm": (body) => {
        sent.push(body);
        return String(body!.last_group).toUpperCase() === "ZD6JF" // the core compares without case
          ? Response.json({ saved: true })
          : Response.json({ error: { en: "That is not the last group.", ar: "دي مش آخر مجموعة." } }, { status: 422 });
      },
    });
    const done = vi.fn();
    const user = userEvent.setup();
    render(<RecoveryCode code={CODE} confirmPath="/backup/recovery-code/confirm" onDone={done} />);
    expect(screen.getByRole("status", { name: texts.recoveryTitle.en })).toHaveTextContent(CODE);
    await user.click(screen.getByRole("button", { name: texts.recoverySaved.en }));
    const box = screen.getByLabelText(texts.recoveryLastGroup.en);
    await user.type(box, "AAAA");
    expect(sent).toEqual([]); // not a whole group yet: nothing sent
    await user.type(box, "A"); // the fifth: checked at once, no Confirm button
    expect(await screen.findByRole("alert")).toHaveTextContent("That is not the last group.");
    expect(box).toHaveValue("AAAAA"); // kept, to be fixed
    expect(screen.queryByRole("button", { name: /confirm/i })).toBeNull();
    expect(done).not.toHaveBeenCalled();
    await user.clear(box);
    await user.type(box, "zd6jf ");
    await waitFor(() => expect(done).toHaveBeenCalledOnce());
    expect(sent.at(-1)).toEqual({ last_group: "zd6jf" });
  });

  it("Confidential on shows the project's code once; off asks first", async () => {
    const project = { id: "p1", name: "برج - عينة", created_at: "x" };
    setCurrentProject(project);
    const puts: unknown[] = [];
    mockCore({
      "PUT /projects/p1/confidential": (body) => {
        puts.push(body);
        return body!.on ? Response.json({ confidential: true, code: CODE }) : Response.json({ confidential: false });
      },
      "POST /projects/p1/confidential/confirm": () => Response.json({ saved: true }),
    });
    const user = userEvent.setup();
    const { rerender } = render(<Confidential project={project} onClose={() => undefined} />);
    await user.click(screen.getByRole("button", { name: texts.confidentialTurnOn.en }));
    expect(await screen.findByText(CODE)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.recoverySaved.en }));
    await user.type(screen.getByLabelText(texts.recoveryLastGroup.en), "ZD6JF");
    await waitFor(() => expect(screen.queryByText(CODE)).toBeNull()); // gone once saved

    rerender(<Confidential project={{ ...project, confidential: true }} onClose={() => undefined} />);
    await user.click(screen.getByRole("button", { name: texts.confidentialTurnOff.en }));
    expect(puts).toHaveLength(1); // nothing sent before the confirm
    expect(screen.getByText(texts.confidentialOffConfirm.en)).toBeInTheDocument();
    const confirm = screen.getAllByRole("button", { name: texts.confidentialTurnOff.en }).at(-1)!;
    await user.click(confirm);
    await waitFor(() => expect(puts).toEqual([{ on: true }, { on: false }]));
  });
});

describe("the Backup panel", () => {
  it("takes the backup folder from the system dialog", async () => {
    vi.stubGlobal("isTauri", true); // One's window: Tauri sets it
    const asked: unknown[] = [];
    mockIPC((cmd, args) => {
      if (cmd === "plugin:dialog|open") {
        asked.push(args);
        return "/home/x/Backups/One";
      }
    });
    const puts: unknown[] = [];
    mockCore({
      "GET /backup": () => Response.json(status()),
      "PUT /backup/folder": (body) => {
        puts.push(body);
        return Response.json(status({ folder: body!.path }));
      },
    });
    const user = userEvent.setup();
    render(<BackupPanel onClose={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: texts.backupPickFolder.en }));
    expect(asked).toEqual([{ options: expect.objectContaining({ directory: true, multiple: false }) }]);
    await waitFor(() => expect(puts).toEqual([{ path: "/home/x/Backups/One" }]));
    expect(await screen.findByText("/home/x/Backups/One")).toBeInTheDocument();
    expect(screen.queryByLabelText(texts.backupFolderPath.en)).toBeNull(); // no path field in One's window
  });

  it("in a plain browser takes a typed path; backs up now; offers a recovery code without an account", async () => {
    mockCore({
      "GET /backup": () =>
        Response.json(status({ folder: "/home/x/Backups", projects: [{ id: "p1", last_backup: "2026-11-05T07:30:00Z", confidential: false }] })),
      "POST /backup/run": () => Response.json({ backed_up: 2 }),
      "POST /backup/recovery-code": () => Response.json({ code: CODE }),
    });
    const user = userEvent.setup();
    render(<BackupPanel onClose={() => undefined} />);
    expect(await screen.findByLabelText(texts.backupFolderPath.en)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.backupNow.en }));
    expect(await screen.findByText(fill(texts.backupDone.en, { n: 2 }))).toBeInTheDocument();
    expect(screen.getByText(texts.backupKeyNoAccount.en)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.backupKeyMakeCode.en }));
    expect(await screen.findByText(CODE)).toBeInTheDocument();
  });

  it("in a plain browser, a typed folder is used on leaving the field, and stays there when refused", async () => {
    const refused = { en: "That folder cannot be used (sample).", ar: "الفولدر ده مينفعش (عينة)." };
    const puts: unknown[] = [];
    mockCore({
      "GET /backup": () => Response.json(status({ folder: null })),
      "PUT /backup/folder": (body) => {
        puts.push(body);
        return Response.json({ error: refused }, { status: 422 });
      },
    });
    const user = userEvent.setup();
    render(<BackupPanel onClose={() => undefined} />);
    const field = await screen.findByLabelText(texts.backupFolderPath.en);
    await user.type(field, "/home/x/Backups");
    expect(puts).toEqual([]); // never half typed
    await user.tab();
    expect(await screen.findByText(refused.en)).toBeInTheDocument();
    expect(puts).toEqual([{ path: "/home/x/Backups" }]);
    expect(field).toHaveValue("/home/x/Backups");
  });

  it("says when the backup folder cannot be reached", async () => {
    const note = { en: "The backup folder could not be reached on 5 Nov.", ar: "فولدر النسخ ماكانش متاح يوم ٥ نوفمبر." };
    mockCore({ "GET /backup": () => Response.json(status({ folder: "/mnt/usb", reachable: false, note })) });
    render(<BackupPanel onClose={() => undefined} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(note.en);
  });
});

describe("restore", () => {
  it("asks each project only for what it needs", async () => {
    let restored: string[] = [];
    const sent: unknown[] = [];
    const all = [
      { id: "a", name: "مدرسة - عينة", last_backup: "2026-11-04T08:00:00Z", needs: null },
      { id: "b", name: "برج - عينة", last_backup: "2026-11-04T08:00:00Z", needs: "backup_code" },
      { id: "c", name: null, last_backup: "2026-11-04T08:00:00Z", needs: "project_code" },
      { id: "d", name: "مستشفى - عينة", last_backup: "2026-11-04T08:00:00Z", needs: "sign_in" },
    ];
    mockCore({
      "GET /backup/found": (_, url) => {
        expect(url).toBe(`/backup/found?path=${encodeURIComponent("/media/usb/One")}`);
        return Response.json({ projects: all.filter((p) => !restored.includes(p.id)) });
      },
      "POST /backup/restore": (body) => {
        sent.push(body);
        restored = [...restored, body!.project_id as string];
        return Response.json({ name: all.find((p) => p.id === body!.project_id)!.name ?? "سري" });
      },
    });
    const user = userEvent.setup();
    render(<Restore />);
    await user.type(screen.getByLabelText(texts.backupFolderPath.en), "/media/usb/One");
    expect(screen.queryByRole("button", { name: texts.restorePickFolder.en })).toBeNull(); // the path is used on Enter
    await user.keyboard("{Enter}");

    const row = (name: string) => screen.getByText(name).closest("li")!;
    await screen.findByText("مدرسة - عينة");
    expect(within(row("مدرسة - عينة")).queryByRole("textbox")).toBeNull();
    expect(within(row("برج - عينة")).getByText(texts.restoreNeedsBackupCode.en)).toBeInTheDocument();
    expect(within(row(texts.restoreHiddenName.en)).getByText(texts.restoreNeedsProjectCode.en)).toBeInTheDocument();
    expect(within(row("مستشفى - عينة")).getByRole("button", { name: texts.restoreNeedsSignIn.en })).toBeInTheDocument();
    expect(within(row("مستشفى - عينة")).queryByRole("textbox")).toBeNull();

    await user.click(within(row("مدرسة - عينة")).getByRole("button", { name: texts.restoreProject.en }));
    expect(await screen.findByText(fill(texts.restoreDone.en, { name: "مدرسة - عينة" }))).toBeInTheDocument();
    await user.type(within(row("برج - عينة")).getByRole("textbox"), CODE);
    await user.click(within(row("برج - عينة")).getByRole("button", { name: texts.restoreProject.en }));
    await waitFor(() => expect(screen.queryByText("برج - عينة")).toBeNull()); // the list is read again after each
    expect(sent).toEqual([
      { path: "/media/usb/One", project_id: "a" },
      { path: "/media/usb/One", project_id: "b", code: CODE },
    ]);
  });
});

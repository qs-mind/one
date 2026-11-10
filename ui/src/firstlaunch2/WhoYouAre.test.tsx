import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { client } from "@/api/client";
import { scenario, server, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { engineer } from "@/texts/engineer";
import { firstlaunch } from "@/texts/firstlaunch";
import { text } from "@/texts/useText";
import { older, serveFirstLaunch } from "./fakeCoreFirstLaunch";
import { WhoYouAre } from "./WhoYouAre";

startFakeCore();
serveFirstLaunch();
beforeEach(stubBrowser);
afterEach(resetPage);

const saved = async () => (await client.GET("/engineer/profile")).data!;

async function choose(label: string, option: string) {
  await userEvent.click(screen.getByRole("combobox", { name: label }));
  await userEvent.click(await screen.findByRole("option", { name: option }));
}

describe.each(DIRS)("Who you are (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }) => text(pair, lang);
  const field = (pair: { en: string; ar: string }) => screen.getByRole("textbox", { name: say(pair) });

  function open() {
    const onNext = vi.fn();
    const onBack = vi.fn();
    renderIn(dir, <WhoYouAre onNext={onNext} onBack={onBack} />);
    return { onNext, onBack };
  }

  it("opens on what the core knows; the seven fields are there", async () => {
    scenario("profile:incomplete"); // from the old introduction card: the choices are known, the texts are not
    open();
    expect(await screen.findByRole("combobox", { name: say(engineer.org_type) })).toHaveTextContent(say(engineer.contractor));
    expect(screen.getByRole("combobox", { name: say(engineer.country) })).toHaveTextContent(say(engineer.EG));
    expect(screen.getByRole("combobox", { name: say(engineer.currency) })).toHaveTextContent("EGP");
    for (const pair of [engineer.first_name, engineer.last_name, engineer.position, engineer.company]) expect(field(pair)).toHaveValue("");
    expect(field(engineer.position)).toHaveAttribute("placeholder", say(engineer.positionExample));
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
  });

  it("saves as the engineer types, with no Save button", async () => {
    scenario("profile:incomplete");
    open();
    await userEvent.type(await screen.findByRole("textbox", { name: say(engineer.first_name) }), "مهندس");
    await waitFor(async () => expect((await saved()).first_name).toBe("مهندس"));
    expect((await saved()).complete).toBe(false); // a half-filled profile is kept too
  });

  it("cannot go on until the seven fields are filled, and says what is missing", async () => {
    scenario("profile:incomplete");
    const { onNext } = open();
    await screen.findByRole("textbox", { name: say(engineer.first_name) });
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    expect(await screen.findByText(say(firstlaunch.fillEvery))).toBeInTheDocument();
    expect(screen.getAllByText(say(engineer.missingText))).toHaveLength(4);
    expect(field(engineer.first_name)).toHaveAttribute("aria-invalid", "true");
    expect(onNext).not.toHaveBeenCalled();

    await userEvent.type(field(engineer.first_name), "مهندس");
    await userEvent.type(field(engineer.last_name), "تجريبي");
    await userEvent.type(field(engineer.position), "مدير المكتب الفني");
    await userEvent.type(field(engineer.company), "شركة مقاولات");
    expect(screen.queryByText(say(engineer.missingText))).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    await waitFor(() => expect(onNext).toHaveBeenCalledOnce());
    expect((await saved()).complete).toBe(true);
  });

  it("an empty profile needs every choice too; a country fills its usual currency", async () => {
    server.use(
      http.get("*/api/engineer/profile", () =>
        HttpResponse.json({ first_name: "", last_name: "", position: "", company: "", org_type: null, country: null, currency: null, complete: false }),
      ),
    );
    open();
    await screen.findByRole("textbox", { name: say(engineer.first_name) });
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    expect(await screen.findAllByText(say(engineer.missingChoice))).toHaveLength(3);
    await choose(say(engineer.country), say(engineer.SA));
    expect(screen.getByRole("combobox", { name: say(engineer.currency) })).toHaveTextContent("SAR");
    await choose(say(engineer.org_type), say(engineer.procurement));
    expect(screen.queryByText(say(engineer.missingChoice))).toBeNull();
  });

  it("a name the core refuses shows the core's words in that field", async () => {
    scenario("profile:incomplete");
    open();
    const first = await screen.findByRole("textbox", { name: say(engineer.first_name) });
    await userEvent.click(first);
    await userEvent.paste("م".repeat(81));
    expect(await screen.findByText(lang === "ar" ? "ده طويل زيادة. اكتب 80 حرف بالكتير." : "This is too long. Write 80 characters at most.")).toBeInTheDocument();
    expect(first).toHaveAttribute("aria-invalid", "true");
  });

  it("a profile that cannot be saved says so, and Next stays here", async () => {
    scenario("profile");
    server.use(http.put("*/api/engineer/profile", () => HttpResponse.json({}, { status: 503 })));
    const { onNext } = open();
    await screen.findByRole("textbox", { name: say(engineer.first_name) });
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.next) }));
    expect(await screen.findByText(say(engineer.notSaved))).toBeInTheDocument();
    expect(onNext).not.toHaveBeenCalled();
  });

  it("signing in fills an empty name", async () => {
    scenario("profile:incomplete");
    open();
    await userEvent.click(await screen.findByRole("button", { name: say(firstlaunch.signIn) }));
    expect(await screen.findByText(say(firstlaunch.signingIn))).toBeInTheDocument();
    expect(older.calls).toContain(`POST /account/sign-in {"locale":"${lang}","device":false}`);
    await waitFor(() => expect(field(engineer.first_name)).toHaveValue("مهندس"), { timeout: 3000 });
    expect(field(engineer.last_name)).toHaveValue("تجريبي");
    expect(screen.getByText(/engineer@example\.com/)).toBeInTheDocument();
  });

  it("Back keeps what was typed", async () => {
    scenario("profile:incomplete");
    const { onBack } = open();
    await userEvent.type(await screen.findByRole("textbox", { name: say(engineer.company) }), "شركة");
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.back) }));
    expect(onBack).toHaveBeenCalledOnce();
    await waitFor(async () => expect((await saved()).company).toBe("شركة"));
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { firstlaunch } from "@/texts/firstlaunch";
import { text } from "@/texts/useText";
import { ConnectAi } from "./ConnectAi";
import { older, serveFirstLaunch } from "./fakeCoreFirstLaunch";

startFakeCore();
serveFirstLaunch();
beforeEach(stubBrowser);
afterEach(resetPage);

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");

describe.each(DIRS)("Connect AI (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string>) => text(pair, lang, vars);
  const keyBox = () => screen.getByLabelText(say(firstlaunch.keyLabel));

  function open() {
    const onDone = vi.fn();
    renderIn(dir, <ConnectAi onBack={() => {}} onDone={onDone} />);
    return { onDone };
  }

  async function agree() {
    await userEvent.click(await screen.findByRole("button", { name: say(firstlaunch.agree) }));
    await screen.findByText(say(firstlaunch.agreed));
  }

  it("asks the AI consent first: no key and no Claude Code before it", async () => {
    open();
    await screen.findByRole("button", { name: say(firstlaunch.agree) });
    expect(keyBox()).toBeDisabled();
    expect(screen.getByRole("button", { name: say(firstlaunch.useClaudeCode) })).toHaveAttribute("data-disabled");
    expect(screen.getByText(say(firstlaunch.keyAfterConsent))).toBeInTheDocument();
    await agree();
    expect(older.calls).toContain('PUT /settings/ai-consent {"text_version":3}'); // the version the core asked for
    expect(keyBox()).toBeEnabled();
  });

  it("a pasted key is checked at once and names the provider; Start passes the step", async () => {
    const { onDone } = open();
    await agree();
    await userEvent.click(keyBox());
    await userEvent.paste("sk-ant-sample-key");
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(firstlaunch.keyWorks, { provider: "Anthropic" }))));
    expect(document.body.textContent).not.toContain("sk-ant-sample-key");
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.start) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(older.calls).toContain('PUT /setup/ai {"state":"done"}');
  });

  it("a key ONE does not know shows the core's plain words", async () => {
    open();
    await agree();
    await userEvent.click(keyBox());
    await userEvent.paste("x");
    const words = lang === "ar" ? "ONE مش عارف المفتاح ده. اتأكد إنك نسخته كله." : "ONE does not recognise this key. Check that you copied all of it.";
    expect(await screen.findByText(words)).toBeInTheDocument();
    expect(keyBox()).toHaveAttribute("aria-invalid", "true");
    expect(screen.queryByRole("button", { name: say(firstlaunch.start) })).toBeNull();
  });

  it("for a key ONE does not know, the provider's address links it with no button", async () => {
    const { onDone } = open();
    await agree();
    await userEvent.click(keyBox());
    await userEvent.paste("x-unknown-key");
    const address = await screen.findByLabelText(say(firstlaunch.addressLabel));
    await userEvent.type(address, "ftp://example.com");
    await userEvent.tab();
    expect(await screen.findByText(say(firstlaunch.addressBad))).toBeInTheDocument();
    expect(older.calls.some((call) => call.startsWith("POST /settings/ai/standard"))).toBe(false);
    await userEvent.clear(address);
    await userEvent.type(address, "https://api.example.com/v1{Enter}");
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(firstlaunch.addressLinked, { provider: "api.example.com" }))));
    expect(older.calls).toContain('POST /settings/ai/standard {"name":"api.example.com","base_url":"https://api.example.com/v1","key":"x-unknown-key"}');
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.start) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(older.calls).toContain('PUT /setup/ai {"state":"done"}');
  });

  it("after a refused save the same address can be sent again", async () => {
    older.standardRefuses = 1;
    open();
    await agree();
    await userEvent.click(keyBox());
    await userEvent.paste("x-unknown-key");
    const address = await screen.findByLabelText(say(firstlaunch.addressLabel));
    await userEvent.type(address, "https://api.example.com/v1{Enter}");
    const words = lang === "ar" ? "ONE ماقدرش يحفظ المفتاح دلوقتي. جرّب تاني." : "ONE could not keep the key just now. Try again.";
    expect(await screen.findByText(words)).toBeInTheDocument();
    await userEvent.type(address, "{Enter}");
    await waitFor(() => expect(plain(document.body.textContent)).toContain(plain(say(firstlaunch.addressLinked, { provider: "api.example.com" }))));
    expect(older.calls.filter((call) => call.startsWith("POST /settings/ai/standard"))).toHaveLength(2);
  });

  it("the engineer's own Claude Code is the other way", async () => {
    const { onDone } = open();
    await agree();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.useClaudeCode) }));
    expect(await screen.findByText(say(firstlaunch.claudeWorks))).toBeInTheDocument();
    expect(older.calls).toContain('POST /settings/ai/check {"via":"claude_code"}');
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.start) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
  });

  it("a Claude Code that is missing, or does not answer, says so in words", async () => {
    older.claudeCode.found = false;
    open();
    await agree();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.useClaudeCode) }));
    expect(await screen.findByText(say(firstlaunch.claudeMissing))).toBeInTheDocument();
    older.claudeCode = { found: true, answers: false };
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.tryAgain) }));
    const words = lang === "ar" ? "Claude Code مش داخل بحساب. ادخل بحسابك فيه، وبعدين جرّب تاني." : "Claude Code is not signed in. Sign in to it, then try again.";
    expect(await screen.findByText(words)).toBeInTheDocument();
  });

  it("an AI the core holds already (the step seen before, then Back) shows Start, not Later", async () => {
    older.consent = { at: "2026-11-10T09:00:00.000000+00:00", text_version: 3 };
    older.links = [{ id: "anthropic", kind: "model", name: "Claude", provider: "Anthropic", on_device: false, key_set: true, error: null }];
    const { onDone } = open();
    await userEvent.click(await screen.findByRole("button", { name: say(firstlaunch.start) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(older.calls).toContain('PUT /setup/ai {"state":"done"}');
    expect(screen.queryByText(say(firstlaunch.laterNote))).toBeNull();
  });

  it("with no AI the step can be left for later", async () => {
    const { onDone } = open();
    expect(await screen.findByText(say(firstlaunch.laterNote))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: say(firstlaunch.later) }));
    await waitFor(() => expect(onDone).toHaveBeenCalledOnce());
    expect(older.calls).toContain('PUT /setup/ai {"state":"skipped"}');
  });
});

// A reload of the settings (on a reconnect) that the core answered before a change was saved must not put the old
// value back over the change.
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client } from "@/api/client";
import { server, startFakeCore } from "@/api/fakeCore";
import { resetPage, stubBrowser } from "@/design/test/harness";
import { useSettings } from "./useSettings";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

describe("useSettings", () => {
  it("a reload answered before a change does not undo the change", async () => {
    const { result } = renderHook(() => useSettings());
    await waitFor(() => expect(result.current.loaded.state).toBe("ready"));
    const before = (await client.GET("/settings")).data!; // what the core held before the change
    const models = before.settings.find((it) => it.key === "ai.models")!;
    let answer!: () => void;
    const held = new Promise<void>((resolve) => (answer = resolve));
    server.use(http.get("*/api/settings", async () => (await held, HttpResponse.json(before)), { once: true }));

    let reload!: Promise<void>;
    act(() => void (reload = result.current.load()));
    await act(async () => void (await result.current.change("ai.models", "own")));
    await act(async () => (answer(), await reload));

    const now = result.current.loaded;
    expect(now.state === "ready" && now.settings.find((it) => it.key === models.key)?.value).toBe("own");
  });
});

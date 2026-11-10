// The settings as the core keeps them (GET /settings), kept current by the `setting` event (the Lead may change one
// by talking), and the one way to change one: PATCH /settings/{key}, which saves at once and answers the setting as
// stored. The screen's own change never asks first (contract 21-22): the engineer is the one changing it.
import { useCallback, useEffect, useRef, useState } from "react";
import { subscribeGeneral } from "@/activity";
import { client, type Schemas } from "@/api/client";
import type { TextPair } from "@/texts/types";
import { applyLook } from "./look";

export type Setting = Schemas["Settings"]["settings"][number];
export type Loaded = { state: "loading" } | { state: "failed" } | { state: "ready"; settings: Setting[] };

/** What one change came to: the setting as stored, or the core's words (with its `example` when it gave one). */
export type Saved = { setting: Setting } | { words: TextPair | null; example?: string | null };

export function useSettings() {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  // The settings changed while a load is on its way: its answer may be older, so they are laid over it.
  const during = useRef(new Set<Map<string, Setting>>());

  const put = useCallback((setting: Setting) => {
    for (const changed of during.current) changed.set(setting.key, setting);
    applyLook(setting);
    setLoaded((now) =>
      now.state === "ready" ? { state: "ready", settings: now.settings.map((it) => (it.key === setting.key ? setting : it)) } : now,
    );
  }, []);

  const load = useCallback(async () => {
    const changed = new Map<string, Setting>();
    during.current.add(changed);
    try {
      const { data } = await client.GET("/settings");
      const settings = data?.settings.map((it) => changed.get(it.key) ?? it);
      setLoaded(settings ? { state: "ready", settings } : { state: "failed" });
    } catch {
      setLoaded({ state: "failed" });
    } finally {
      during.current.delete(changed);
    }
  }, []);

  useEffect(() => {
    // Listen first, then load: a change made in between is not lost (and after a reconnect, load again).
    const stop = subscribeGeneral((event) => event.type === "setting" && put(event.setting), () => void load());
    void load();
    return stop;
  }, [load, put]);

  const change = useCallback(
    async (key: string, value: boolean | string): Promise<Saved> => {
      try {
        const { data, error } = await client.PATCH("/settings/{key}", { params: { path: { key } }, body: { value } });
        if (data) {
          put(data);
          return { setting: data };
        }
        if (error && "error" in error) return { words: error.error, example: error.example };
      } catch {
        // the core could not be reached
      }
      return { words: null };
    },
    [put],
  );

  return { loaded, load, change };
}

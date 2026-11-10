// What Home shows, from GET /home and the profile's first name, kept current by the `home` event on the general
// stream (which only says "load it again"). It listens first, then loads, and loads again when the stream comes back,
// so nothing said meanwhile is missed (contract 3.4).
import { useCallback, useEffect, useState } from "react";
import { subscribeGeneral } from "@/activity";
import { client, type Schemas } from "@/api/client";

export type HomeState =
  | { status: "loading" }
  | { status: "failed" }
  | { status: "ready"; home: Schemas["Home"]; firstName: string };

export function useHome(): { state: HomeState; reload: () => void } {
  const [home, setHome] = useState<Schemas["Home"] | null | undefined>(); // null: the core could not answer
  const [firstName, setFirstName] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    const load = () =>
      void client
        .GET("/home")
        .then(({ data }) => live && setHome((was) => data ?? was ?? null))
        .catch(() => live && setHome((was) => was ?? null));
    const stop = subscribeGeneral((event) => event.type === "home" && load(), load);
    load();
    client
      .GET("/engineer/profile")
      .then(({ data }) => live && data && setFirstName(data.first_name.trim()))
      .catch(() => undefined); // no name: the greeting goes without one
    return () => {
      live = false;
      stop();
    };
  }, [tick]);

  const reload = useCallback(() => {
    setHome(undefined);
    setTick((n) => n + 1);
  }, []);

  if (home === undefined) return { state: { status: "loading" }, reload };
  if (home === null) return { state: { status: "failed" }, reload };
  return { state: { status: "ready", home, firstName }, reload };
}

// My profile: the seven fields first launch asked (the shared schema and fields, @/engineer/profile and U7's
// ProfileFields), saved as the engineer types (PUT /engineer/profile, a moment after the last key), and under them
// the QS Mind account (Account) and what the Lead QS learned about the engineer's work (Lessons).
import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { client } from "@/api/client";
import { FIELDS, type FieldName, formOf, type ProfileForm, type ProfileValid, profileSchema, toProfileIn } from "@/engineer/profile";
import { ProfileFields, type Refused } from "@/firstlaunch/ProfileFields";
import { engineer } from "@/texts/engineer";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { Account } from "./Account";
import { Lessons } from "./Lessons";

/** How long after the last key the profile is saved. */
export const SAVE_MS = 400;

const isField = (name: unknown): name is FieldName => (FIELDS as readonly unknown[]).includes(name);
type Status = { state: "kept" } | { state: "saving" } | { state: "saved" } | { state: "unsaved"; words: TextPair };

export function MyProfile() {
  const t = useText();
  const form = useForm<ProfileForm, unknown, ProfileValid>({ resolver: zodResolver(profileSchema), mode: "onChange" });
  const [loaded, setLoaded] = useState<"loading" | "ready" | "failed">("loading");
  const [refused, setRefused] = useState<Refused>(null);
  const [status, setStatus] = useState<Status>({ state: "kept" });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  useEffect(() => {
    let live = true;
    void client
      .GET("/engineer/profile")
      .then(({ data }) => {
        if (!live) return;
        if (data) form.reset(formOf(data));
        setLoaded(data ? "ready" : "failed");
      })
      .catch(() => live && setLoaded("failed"));
    return () => {
      live = false;
    };
  }, [form]);

  // Saves as the engineer goes; a half-filled profile is saved too, and the schema says what is missing.
  useEffect(() => {
    if (loaded !== "ready") return;
    async function save() {
      setStatus({ state: "saving" });
      try {
        const { data, error } = await client.PUT("/engineer/profile", { body: toProfileIn(form.getValues()) });
        if (data) {
          setRefused(null);
          return setStatus({ state: "saved" });
        }
        const words = error && "error" in error ? error.error : undefined;
        if (words && error && "field" in error && isField(error.field)) {
          setRefused({ field: error.field, words });
          return setStatus({ state: "kept" });
        }
        setStatus({ state: "unsaved", words: words ?? engineer.notSaved });
      } catch {
        setStatus({ state: "unsaved", words: engineer.notSaved });
      }
    }
    const watching = form.watch(() => {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void save(), SAVE_MS);
    });
    return () => {
      watching.unsubscribe();
      clearTimeout(timer.current);
    };
  }, [form, loaded]);

  const line =
    status.state === "saving" ? t(texts.saving) : status.state === "saved" ? t(texts.saved) : status.state === "unsaved" ? t(status.words) : t(engineer.kept);
  return (
    <>
      {loaded === "ready" ? (
        <form noValidate onSubmit={(event) => event.preventDefault()} className="flex flex-col gap-4">
          <ProfileFields form={form} refused={refused} />
          <p aria-live="polite" className={status.state === "unsaved" ? "text-xs font-bold" : "text-xs text-muted-foreground"}>
            {line}
          </p>
        </form>
      ) : loaded === "loading" ? (
        <div aria-busy="true" className="min-h-14" />
      ) : (
        <p className="text-xs font-bold">{t(texts.notLoaded)}</p>
      )}
      <Account />
      <Lessons />
    </>
  );
}

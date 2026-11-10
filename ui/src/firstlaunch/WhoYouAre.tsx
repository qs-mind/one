// Step 2: who you are. The seven fields of the profile, saved as the engineer types (PUT /engineer/profile, a
// moment after the last key; a half-filled profile is saved too) and checked by the schema Settings shares. There is
// no Save button: Next saves what is left and goes on only when the schema passes and the core says `complete`.
// Signing in fills the name.
import { zodResolver } from "@hookform/resolvers/zod";
import { useCallback, useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { client, type Schemas } from "@/api/client";
import type { Account } from "@/api/existing";
import { Button } from "@/design/ui/button";
import { Separator } from "@/design/ui/separator";
import { FIELDS, type FieldName, formOf, type ProfileForm, type ProfileValid, profileSchema, toProfileIn } from "@/engineer/profile";
import { engineer } from "@/texts/engineer";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { StepActions, StepHead } from "./parts";
import { ProfileFields, type Refused } from "./ProfileFields";
import { SignIn } from "./SignIn";

/** How long after the last key the profile is saved. */
export const SAVE_MS = 400;

const EMPTY: ProfileForm = { first_name: "", last_name: "", position: "", company: "", org_type: "", country: "", currency: "" };
const isField = (name: unknown): name is FieldName => (FIELDS as readonly unknown[]).includes(name);

/** With no `onBack` there is no Back (someone upgrading lands on this step only). */
export function WhoYouAre({ onBack, onNext }: { onBack?: () => void; onNext: () => void }) {
  const t = useText();
  const form = useForm<ProfileForm, unknown, ProfileValid>({
    resolver: zodResolver(profileSchema),
    defaultValues: EMPTY,
    mode: "onSubmit",
    reValidateMode: "onChange",
  });
  const [loaded, setLoaded] = useState(false);
  const [refused, setRefused] = useState<Refused>(null);
  const [unsaved, setUnsaved] = useState<TextPair>();
  const [held, setHeld] = useState(false); // Next was pressed with a field missing
  const [busy, setBusy] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  const save = useCallback(async (values: ProfileForm): Promise<Schemas["Profile"] | undefined> => {
    clearTimeout(timer.current);
    try {
      const { data, error } = await client.PUT("/engineer/profile", { body: toProfileIn(values) });
      if (data) {
        setRefused(null);
        setUnsaved(undefined);
        return data;
      }
      const words = error && "error" in error ? error.error : undefined;
      if (words && error && "field" in error && isField(error.field)) setRefused({ field: error.field, words });
      else setUnsaved(words ?? engineer.notSaved);
    } catch {
      setUnsaved(engineer.notSaved); // the core could not be reached
    }
    return undefined;
  }, []);

  useEffect(() => {
    let live = true;
    void client
      .GET("/engineer/profile")
      .then(({ data }) => live && data && form.reset(formOf(data)))
      .catch(() => undefined)
      .finally(() => live && setLoaded(true));
    return () => {
      live = false;
    };
  }, [form]);

  // Saves as the engineer goes, a moment after the last change.
  useEffect(() => {
    if (!loaded) return;
    const watching = form.watch(() => {
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void save(form.getValues()), SAVE_MS);
    });
    return () => {
      watching.unsubscribe();
      clearTimeout(timer.current);
    };
  }, [form, loaded, save]);

  // Signed in: the core fills the name from the account; an empty name field takes it.
  const signedIn = useCallback(
    async (account: Account) => {
      const known = await client.GET("/engineer/profile").catch(() => undefined);
      const [first = "", ...rest] = (account.name ?? "").trim().split(/\s+/);
      const names = { first_name: known?.data?.first_name || first, last_name: known?.data?.last_name || rest.join(" ") };
      for (const name of ["first_name", "last_name"] as const)
        if (form.getValues(name).trim() === "" && names[name] !== "") form.setValue(name, names[name], { shouldValidate: form.formState.isSubmitted });
    },
    [form],
  );

  const next = form.handleSubmit(
    async (_valid, event) => {
      event?.preventDefault();
      setHeld(false);
      setBusy(true);
      const saved = await save(form.getValues());
      setBusy(false);
      if (saved?.complete) onNext();
      else if (saved) setHeld(true);
    },
    () => setHeld(true),
  );

  const note = unsaved ? t(unsaved) : held ? t(firstlaunch.fillEvery) : t(engineer.kept);
  return (
    <>
      <StepHead title={t(firstlaunch.whoTitle)} lead={t(firstlaunch.whoLead)} />
      <SignIn onSignedIn={signedIn} />
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <Separator className="flex-1" />
        <span>{t(firstlaunch.orType)}</span>
        <Separator className="flex-1" />
      </div>
      <form noValidate onSubmit={(event) => void next(event)} className="flex flex-col gap-10">
        {loaded ? <ProfileFields form={form} refused={refused} /> : null}
        <StepActions note={note} strong={Boolean(unsaved) || held}>
          {onBack ? (
            <Button
              type="button"
              variant="ghost"
              size="lg"
              onClick={() => {
                void save(form.getValues()); // nothing typed is lost on the way back
                onBack();
              }}
            >
              {t(firstlaunch.back)}
            </Button>
          ) : null}
          <Button type="submit" size="lg" loading={busy} disabled={!loaded}>
            {t(firstlaunch.next)}
          </Button>
        </StepActions>
      </form>
    </>
  );
}

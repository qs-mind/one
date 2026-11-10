// With `ai.models` on "own": a model for each role, from the models the connected providers list (GET /settings/ai,
// `sheet`), saved when one is chosen (the existing PUT /settings/ai/roles).
import { useState } from "react";
import { type AiSettings, chooseModel, type ModelChoice, type Role, ROLES } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

/** One select value per model: the same model always gives the same text. */
const keyOf = (choice: ModelChoice) => JSON.stringify([choice.connector, choice.model]);

export function RolePicker({ ai }: { ai: AiSettings }) {
  const t = useText();
  const [roles, setRoles] = useState(ai.roles);
  const [saved, setSaved] = useState<Partial<Record<Role, "saving" | "saved" | TextPair>>>({});
  const items = ai.sheet.map((card) => ({ value: keyOf(card), label: `${card.name} (${card.provider})` }));

  async function choose(role: Role, value: string) {
    const card = ai.sheet.find((it) => keyOf(it) === value);
    if (!card) return;
    setSaved((now) => ({ ...now, [role]: "saving" }));
    const answer = await chooseModel(role, { connector: card.connector, model: card.model });
    if (answer.data) setRoles((now) => ({ ...now, ...answer.data }));
    setSaved((now) => ({ ...now, [role]: answer.data ? "saved" : (answer.error ?? texts.notSaved) }));
  }

  return (
    <section aria-labelledby="roles" className="flex flex-col gap-5">
      <h3 id="roles" className="text-lg font-bold">
        {t(texts.rolesTitle)}
      </h3>
      {ai.sheet.length === 0 ? <p className="text-muted-foreground">{t(texts.noModels)}</p> : null}
      {ai.sheet.length > 0
        ? ROLES.map((role) => {
            const chosen = roles[role] ?? ai.defaults[role];
            const state = saved[role];
            return (
              <Field
                key={role}
                label={t(texts[`role_${role}`])}
                help={state === "saving" ? t(texts.saving) : state === "saved" ? t(texts.saved) : undefined}
                error={typeof state === "object" ? t(state) : undefined}
              >
                <Select items={items} value={chosen ? keyOf(chosen) : null} onValueChange={(value) => typeof value === "string" && void choose(role, value)}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {items.map((item) => (
                      <SelectItem key={item.value} value={item.value}>
                        {item.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
            );
          })
        : null}
    </section>
  );
}

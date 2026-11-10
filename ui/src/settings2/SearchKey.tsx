// The web search key (contract Q21: Settings, AI, with the two existing routes). It says what ONE searches with now;
// a pasted key is kept when the engineer leaves the box or presses Enter, and is never shown back.
import { useCallback, useEffect, useState } from "react";
import { getSearch, saveSearchKey, type SearchState } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

export function SearchKey() {
  const t = useText();
  const [search, setSearch] = useState<SearchState>();
  const [typed, setTyped] = useState("");
  const [saving, setSaving] = useState<"idle" | "saving" | TextPair>("idle");

  const load = useCallback(async () => {
    const answer = await getSearch();
    if (answer.data) setSearch(answer.data);
  }, []);
  useEffect(() => void load(), [load]);

  async function keep() {
    const value = typed.trim();
    if (value === "") return;
    setSaving("saving");
    const answer = await saveSearchKey(value);
    if (answer.data) {
      setTyped("");
      setSaving("idle");
      return void load();
    }
    setSaving(answer.error ?? texts.notSaved);
  }

  const help =
    saving === "saving"
      ? t(texts.searchSaving)
      : search?.own_key
        ? t(texts.searchKept)
        : search?.provider
          ? t(texts.searchBy, { provider: search.provider })
          : t(texts.searchNone);
  return (
    <Field label={t(texts.searchKey)} labelSize="lg" help={help} error={typeof saving === "object" ? t(saving) : undefined}>
      <Input
        type="password"
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        onBlur={() => void keep()}
        onKeyDown={(event) => event.key === "Enter" && void keep()}
      />
    </Field>
  );
}

// Under a key ONE does not recognise (422 KEY_NOT_RECOGNISED, contract routes 23-24): the engineer names the
// provider's address and the existing POST /settings/ai/standard keeps the key for it. It is saved when the engineer
// leaves the box or presses Enter; there is no button. The link is named after the address's host.
import { useState } from "react";
import { addStandard } from "@/api/existing";
import { Field } from "@/design/Field";
import { Input } from "@/design/ui/input";
import { firstlaunch } from "@/texts/firstlaunch";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

type Saving = { state: "idle" } | { state: "saving" } | { state: "linked"; provider: string } | { state: "refused"; words: TextPair };

/** The host of an https:// address, or of an http:// one on this computer (a key never goes in the clear). */
function hostOf(address: string): string | undefined {
  try {
    const url = new URL(address);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    return url.hostname && (url.protocol === "https:" || (url.protocol === "http:" && local)) ? url.hostname : undefined;
  } catch {
    return undefined;
  }
}

export function ProviderAddress({ apiKey, onLinked }: { apiKey: string; onLinked: (linked: boolean) => void }) {
  const t = useText();
  const [address, setAddress] = useState("");
  const [saved, setSaved] = useState(""); // the address sent or kept, so leaving the box again sends nothing
  const [saving, setSaving] = useState<Saving>({ state: "idle" });

  async function save() {
    const base_url = address.trim();
    if (base_url === "" || base_url === saved) return;
    setSaved(base_url);
    const host = hostOf(base_url);
    if (!host) return setSaving({ state: "refused", words: firstlaunch.addressBad });
    setSaving({ state: "saving" });
    const { data, error } = await addStandard({ name: host, base_url, key: apiKey });
    if (data) {
      setSaving({ state: "linked", provider: data.provider ?? host });
      return onLinked(true);
    }
    setSaved(""); // a refused save may be tried again with the same address
    setSaving({ state: "refused", words: error ?? firstlaunch.addressNotSaved });
  }

  const help =
    saving.state === "saving"
      ? t(firstlaunch.addressSaving)
      : saving.state === "linked"
        ? t(firstlaunch.addressLinked, { provider: saving.provider })
        : t(firstlaunch.addressHelp);
  return (
    <Field label={t(firstlaunch.addressLabel)} help={help} error={saving.state === "refused" ? t(saving.words) : undefined}>
      <Input
        type="url"
        dir="ltr"
        autoComplete="off"
        spellCheck={false}
        placeholder="https://"
        value={address}
        onChange={(event) => {
          setAddress(event.target.value);
          if (saving.state === "linked") onLinked(false);
          setSaving({ state: "idle" });
        }}
        onBlur={() => void save()}
        onKeyDown={(event) => {
          if (event.key === "Enter") void save();
        }}
      />
    </Field>
  );
}

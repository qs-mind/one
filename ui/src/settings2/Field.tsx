// One setting, drawn from its data (contract 21-22): a toggle is a boxed row with a checkbox, a choice a group of
// boxed rows with radios, an amount or a number a field. Each shows its recommended value and saves on change: a
// toggle or a choice at once, a typed value when the engineer leaves the box or presses Enter. No Save button.
import { useEffect, useId, useState } from "react";
import { Field } from "@/design/Field";
import { ListRow } from "@/design/ListRow";
import { Num } from "@/design/Num";
import { Button } from "@/design/ui/button";
import { Checkbox } from "@/design/ui/checkbox";
import { Input } from "@/design/ui/input";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { settings as texts } from "@/texts/settings";
import { useText } from "@/texts/useText";
import type { Saved, Setting } from "./useSettings";

export type Change = (key: string, value: boolean | string) => Promise<Saved>;
type Status = { state: "idle" } | { state: "saving" } | { state: "saved" } | { state: "refused"; saved: Extract<Saved, { words: unknown }> };

/** Sends one change and keeps what it came to, for the line under the setting. */
function useSave(key: string, change: Change) {
  const [status, setStatus] = useState<Status>({ state: "idle" });
  async function save(value: boolean | string) {
    setStatus({ state: "saving" });
    const saved = await change(key, value);
    setStatus("setting" in saved ? { state: "saved" } : { state: "refused", saved });
  }
  return { status, save };
}

function useStatusWords(status: Status): { help?: string; error?: string } {
  const t = useText();
  if (status.state === "saving") return { help: t(texts.saving) };
  if (status.state === "saved") return { help: t(texts.saved) };
  if (status.state !== "refused") return {};
  const { words, example } = status.saved;
  const said = t(words ?? texts.notSaved);
  return { error: example ? `${said} ${t(texts.example, { example })}` : said };
}

/** The line under a toggle or a choice: saving, saved, or the core's words. */
function StatusLine({ status }: { status: Status }) {
  const { help, error } = useStatusWords(status);
  return (
    <p aria-live="polite" className={error ? "text-xs font-bold empty:hidden" : "text-xs text-muted-foreground empty:hidden"}>
      {error ?? help}
    </p>
  );
}

function ToggleField({ setting, change }: { setting: Extract<Setting, { control: "toggle" }>; change: Change }) {
  const t = useText();
  const { status, save } = useSave(setting.key, change);
  const recommended = t(texts.recommended, { value: t(setting.recommended ? texts.on : texts.off) });
  return (
    <div className="flex flex-col gap-2">
      <ListRow
        frame="boxed"
        render={<label />}
        leading={<Checkbox checked={setting.value} onCheckedChange={(on) => void save(on)} />}
        title={t(setting.title)}
        meta={t(setting.help)}
        detail={recommended}
      />
      <StatusLine status={status} />
    </div>
  );
}

function ChoiceField({ setting, change }: { setting: Extract<Setting, { control: "choice" }>; change: Change }) {
  const t = useText();
  const id = useId();
  const { status, save } = useSave(setting.key, change);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 id={`${id}-title`} className="text-lg font-bold">
          {t(setting.title)}
        </h3>
        <p id={`${id}-help`} className="text-xs text-muted-foreground">
          {t(setting.help)}
        </p>
      </div>
      <RadioGroup
        aria-labelledby={`${id}-title`}
        aria-describedby={`${id}-help`}
        value={setting.value}
        onValueChange={(next) => typeof next === "string" && next !== setting.value && void save(next)}
        className="gap-3"
      >
        {setting.choices.map((choice) => (
          <ListRow
            key={choice.value}
            frame="boxed"
            render={<label />}
            current={choice.value === setting.value}
            leading={<RadioGroupItem value={choice.value} />}
            title={t(choice.title)}
            meta={choice.value === setting.recommended ? t(texts.recommendedChoice) : undefined}
          />
        ))}
      </RadioGroup>
      <StatusLine status={status} />
    </div>
  );
}

function AmountField({ setting, change }: { setting: Extract<Setting, { control: "money" | "number" }>; change: Change }) {
  const t = useText();
  const [typed, setTyped] = useState(setting.value);
  const { status, save } = useSave(setting.key, change);
  const { help: statusHelp, error } = useStatusWords(status);
  useEffect(() => setTyped(setting.value), [setting.value]); // a value stored elsewhere (the Lead, Put back) shows

  function leave() {
    const value = typed.trim();
    if (value !== setting.value) void save(value);
  }
  const unit = setting.control === "money" ? setting.currency : undefined;
  const recommended = t(texts.recommended, { value: unit ? `${setting.recommended} ${unit}` : setting.recommended });
  const help = (
    <>
      {t(setting.help)} {recommended}
      {setting.control === "number" ? <> {t(texts.range, { min: setting.min, max: setting.max })}</> : null}
      {statusHelp ? <> {statusHelp}</> : null}
    </>
  );
  const input = (
    <Input
      variant={unit ? "bare" : "field"}
      dir="ltr"
      inputMode="decimal"
      autoComplete="off"
      value={typed}
      onChange={(event) => setTyped(event.target.value)}
      onBlur={leave}
      onKeyDown={(event) => event.key === "Enter" && leave()}
    />
  );
  return (
    <div className="flex flex-col gap-1">
      <Field label={t(setting.title)} help={help} error={error}>
        {unit ? (
          <div className="focus-ring-within flex h-13 items-center gap-2 rounded-xl border border-input bg-card px-4 hover:border-muted-foreground has-aria-invalid:border-2 has-aria-invalid:border-foreground has-aria-invalid:px-[calc(--spacing(4)-1px)]">
            {input}
            <span className="shrink-0 text-xs text-muted-foreground">
              <Num>{unit}</Num>
            </span>
          </div>
        ) : (
          input
        )}
      </Field>
      {setting.at_recommended ? null : (
        <Button
          variant="link"
          className="self-start"
          aria-label={`${t(texts.putBack)}: ${t(setting.title)}`}
          onClick={() => void save(setting.recommended)}
        >
          {t(texts.putBack)}
        </Button>
      )}
    </div>
  );
}

export function SettingField({ setting, change }: { setting: Setting; change: Change }) {
  if (setting.control === "toggle") return <ToggleField setting={setting} change={change} />;
  if (setting.control === "choice") return <ChoiceField setting={setting} change={change} />;
  return <AmountField key={setting.key} setting={setting} change={change} />;
}

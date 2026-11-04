// Choose the Lead QS model from the models the engineer's own Claude key can use. The core keeps the choice.
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { pick, t, type Text, texts, useLanguage } from "../i18n";

type ModelInfo = { id: string; name: string };
type List =
  | { state: "idle" | "loading" | "no-key" }
  | { state: "ready"; models: ModelInfo[] }
  | { state: "failed"; line: Text };

// The core sends a failure as {error: {en, ar}}; anything else gets the screen's own line.
async function coreLine(response: Response | undefined, fallback: Text): Promise<Text> {
  const body = (await response?.json().catch(() => undefined)) as { error?: Partial<Text> } | undefined;
  const line = body?.error;
  return typeof line?.en === "string" && typeof line.ar === "string" ? (line as Text) : fallback;
}

/** The model in use and the models the key can use; the list loads as soon as a key is known to be saved. */
export function useModel(keySet: boolean | undefined) {
  const [id, setId] = useState<string>();
  const [list, setList] = useState<List>({ state: "idle" });

  useEffect(() => {
    let live = true;
    fetch("/api/settings/model")
      .then((response) => (response.ok ? (response.json() as Promise<{ id?: unknown }>) : undefined))
      .then((body) => live && typeof body?.id === "string" && setId(body.id))
      .catch(() => undefined); // the header then says "Model"; choosing one still works
    return () => {
      live = false;
    };
  }, []);

  const load = useCallback(async () => {
    setList({ state: "loading" });
    const response = await fetch("/api/settings/models").catch(() => undefined);
    if (response?.ok) setList({ state: "ready", models: (await response.json()) as ModelInfo[] });
    else if (response?.status === 409) setList({ state: "no-key" });
    else setList({ state: "failed", line: await coreLine(response, texts.modelsFailed) });
  }, []);

  useEffect(() => {
    if (keySet) void load();
  }, [keySet, load]);

  const name = list.state === "ready" ? list.models.find((model) => model.id === id)?.name : undefined;
  return { id, name: name ?? id, list, load, setId };
}

export type Model = ReturnType<typeof useModel>;

export function ModelPanel({ model, onClose }: { model: Model; onClose: () => void }) {
  useLanguage();
  const title = useId();
  const toFocus = useRef<HTMLButtonElement>(null);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const { list } = model;
  const models = list.state === "ready" ? list.models : [];
  const focused = models.some((item) => item.id === model.id) ? model.id : models[0]?.id;

  useEffect(() => {
    toFocus.current?.focus(); // keyboard: the model in use is one key press away
  }, [list.state]);

  async function choose(id: string) {
    setSaving(true);
    setFailed(undefined);
    const response = await fetch("/api/settings/model", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ id }),
    }).catch(() => undefined);
    setSaving(false);
    if (response?.ok) {
      model.setId(id);
      onClose();
    } else {
      setFailed(await coreLine(response, texts.modelNotSaved));
    }
  }

  return (
    <section aria-labelledby={title} className="border-b border-stone px-4 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <h2 id={title} className="font-semibold">
            {t("modelTitle")}
          </h2>
          <button type="button" onClick={onClose} className="text-slate hover:text-ink">
            {t("close")}
          </button>
        </div>
        {(list.state === "idle" || list.state === "loading") && <p className="text-slate">{t("modelsLoading")}</p>}
        {list.state === "no-key" && <p>{t("modelsNoKey")}</p>}
        {list.state === "failed" && (
          <div className="flex items-center gap-3">
            <p role="alert" className="text-copper">
              {pick(list.line)}
            </p>
            <button type="button" onClick={() => void model.load()} className="rounded-md border border-ink px-4 py-2">
              {t("retry")}
            </button>
          </div>
        )}
        {list.state === "ready" && (
          <ul className="flex flex-col gap-1">
            {models.map((item) => {
              const inUse = item.id === model.id;
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    ref={item.id === focused ? toFocus : undefined}
                    aria-current={inUse || undefined}
                    disabled={saving}
                    onClick={() => void choose(item.id)}
                    className={`flex w-full items-center justify-between gap-4 rounded-md px-3 py-2 text-start hover:bg-stone disabled:opacity-40 ${inUse ? "bg-stone font-semibold" : ""}`}
                  >
                    <span dir="ltr">
                      {item.name} <span className="font-normal text-slate">{item.id}</span>
                    </span>
                    {inUse && <span>{t("modelInUse")}</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
        {failed && (
          <p role="alert" className="text-copper">
            {pick(failed)}
          </p>
        )}
      </div>
    </section>
  );
}

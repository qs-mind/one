// The AI providers connected now (GET /settings/ai, `connectors`): each with its state and Disconnect, which takes
// it out at once (DELETE /settings/ai/links/{id}) with Undo in a notice for the core's window. Claude Code is not a
// link (contract 23-24): it is an on/off row, switched on by its check and off with PUT /settings/ai/claude-code.
import { useState } from "react";
import { client } from "@/api/client";
import { checkClaudeCode, findClaudeCode } from "@/api/existing";
import { type AiConnector, switchOffClaudeCode, undo } from "@/api/settingsKept";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { notify, notifyUndo } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { Checkbox } from "@/design/ui/checkbox";
import { common } from "@/texts/common";
import { firstlaunch } from "@/texts/firstlaunch";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

/** A provider that answers with a key or an address: everything but Claude Code. */
const isLink = (connector: AiConnector) => connector.kind === "model" && (connector.key_set || connector.id.startsWith("standard:"));

function ProviderRow({ connector, onChanged }: { connector: AiConnector; onChanged: () => void }) {
  const t = useText();
  const [problem, setProblem] = useState<TextPair>();

  async function disconnect() {
    setProblem(undefined);
    const answer = await client.DELETE("/settings/ai/links/{link_id}", { params: { path: { link_id: connector.id } } }).catch(() => undefined);
    if (!answer?.data) return setProblem(answer?.error && "error" in answer.error ? answer.error.error : texts.notDisconnected);
    const { undo: token } = answer.data;
    onChanged();
    notifyUndo(t(texts.disconnected, { name: connector.name }), t(common.undo), () =>
      void undo(token).then((back) => (back ? onChanged() : notify(t(texts.notUndone)))),
    );
  }

  const state = connector.error ? t(connector.error) : t(texts.works);
  return (
    <li className="flex flex-col gap-2">
      <ListRow
        frame="boxed"
        title={<span className="font-bold">{connector.name}</span>}
        meta={<MetaLine items={[connector.provider !== connector.name ? connector.provider : null, connector.on_device ? t(texts.onDevice) : null]} />}
        trailing={
          <>
            <span className={connector.error ? "font-bold text-foreground" : undefined}>{state}</span>
            <Button variant="outline" onClick={() => void disconnect()}>
              {t(texts.disconnect)}
            </Button>
          </>
        }
        className="flex-wrap"
      />
      {problem ? (
        <p role="alert" className="text-xs font-bold">
          {t(problem)}
        </p>
      ) : null}
    </li>
  );
}

function ClaudeCodeRow({ on, onChanged }: { on: boolean; onChanged: () => void }) {
  const t = useText();
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<TextPair>();

  async function turn(next: boolean) {
    setBusy(true);
    setProblem(undefined);
    if (next) {
      const found = await findClaudeCode();
      if (!found.data?.found) setProblem(firstlaunch.claudeMissing);
      else {
        const checked = await checkClaudeCode();
        if (!checked.data) setProblem(checked.error ?? firstlaunch.claudeFailed);
      }
    } else {
      const saved = await switchOffClaudeCode();
      if (!saved.data) setProblem(saved.error ?? texts.notSaved);
    }
    setBusy(false);
    onChanged();
  }

  return (
    <div className="flex flex-col gap-2">
      <ListRow
        frame="boxed"
        render={<label />}
        leading={<Checkbox checked={on} disabled={busy} onCheckedChange={(next) => void turn(next)} />}
        title={t(texts.claudeCode)}
        meta={t(texts.claudeCodeMeta)}
      />
      <p aria-live="polite" className="text-xs empty:hidden">
        {busy ? <span className="text-muted-foreground">{t(firstlaunch.claudeChecking)}</span> : null}
        {problem ? <span className="font-bold">{t(problem)}</span> : null}
      </p>
    </div>
  );
}

export function Providers({ connectors, onChanged }: { connectors: AiConnector[]; onChanged: () => void }) {
  const t = useText();
  const links = connectors.filter(isLink);
  return (
    <section aria-labelledby="providers" className="flex flex-col gap-3">
      <h2 id="providers" className="text-lg font-bold">
        {t(texts.providers)}
      </h2>
      {links.length === 0 ? <p className="text-muted-foreground">{t(texts.noProvider)}</p> : null}
      <ul className="flex flex-col gap-3">
        {links.map((connector) => (
          <ProviderRow key={connector.id} connector={connector} onChanged={onChanged} />
        ))}
      </ul>
      <ClaudeCodeRow on={connectors.some((it) => it.id === "claude-code")} onChanged={onChanged} />
    </section>
  );
}

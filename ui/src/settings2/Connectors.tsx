// Settings, Connectors: the tools from outside ONE the team may use (GET /connectors), each on or off (saved at
// once) and removable, with Undo in a notice for the core's window; and adding one (AddConnector).
import { useCallback, useEffect, useState } from "react";
import { type ConnectorRow, getConnectors, removeConnector, setConnectorOn, undo } from "@/api/settingsKept";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { notify, notifyUndo } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { Checkbox } from "@/design/ui/checkbox";
import { common } from "@/texts/common";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { AddConnector } from "./AddConnector";

function Row({ connector, onChanged }: { connector: ConnectorRow; onChanged: () => void }) {
  const t = useText();
  const [problem, setProblem] = useState<TextPair>();

  async function turn(on: boolean) {
    setProblem(undefined);
    const answer = await setConnectorOn(connector.name, on);
    if (!answer.data) setProblem(answer.error ?? texts.notSaved);
    onChanged();
  }

  async function remove() {
    setProblem(undefined);
    const answer = await removeConnector(connector.name);
    if (!answer.data) return setProblem(answer.error ?? texts.notRemoved);
    const { undo: token } = answer.data;
    onChanged();
    notifyUndo(t(texts.removed, { name: connector.name }), t(common.undo), () =>
      void undo(token).then((back) => (back ? onChanged() : notify(t(texts.notUndone)))),
    );
  }

  return (
    <li className="flex flex-col gap-2">
      <div className="flex items-center gap-3">
        <ListRow
          frame="boxed"
          render={<label />}
          leading={<Checkbox checked={connector.enabled} onCheckedChange={(on) => void turn(on)} />}
          title={connector.name}
          meta={<MetaLine items={[<bdi key="runs" dir="ltr">{connector.runs}</bdi>, t.plural(texts.connectorTools, connector.tools)]} />}
          className="flex-1"
        />
        <Button variant="ghost" onClick={() => void remove()}>
          {t(texts.remove)}
        </Button>
      </div>
      {problem ? (
        <p role="alert" className="text-xs font-bold">
          {t(problem)}
        </p>
      ) : null}
    </li>
  );
}

export function Connectors() {
  const t = useText();
  const [connectors, setConnectors] = useState<ConnectorRow[] | "failed">();

  const load = useCallback(async () => {
    const answer = await getConnectors();
    setConnectors(answer.data ? answer.data.connectors : "failed");
  }, []);
  useEffect(() => void load(), [load]);

  if (connectors === undefined) return <div aria-busy="true" className="min-h-14" />;
  if (connectors === "failed") return <p className="text-xs font-bold">{t(texts.notLoaded)}</p>;
  return (
    <>
      {connectors.length === 0 ? (
        <p className="text-muted-foreground">{t(texts.noConnectors)}</p>
      ) : (
        <ul className="flex flex-col gap-3">
          {connectors.map((connector) => (
            <Row key={connector.name} connector={connector} onChanged={() => void load()} />
          ))}
        </ul>
      )}
      <AddConnector onAdded={() => void load()} />
    </>
  );
}

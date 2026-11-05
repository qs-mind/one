// A client BOQ as boq_import read it: the client's own document, read only. It runs the Sheet viewer with nothing
// editable; each number opens its source (the client's file, sheet, row and cell). It reloads when the file is
// imported again. It is not a Deliverable.
import { useEffect, useState } from "react";
import type { SheetView } from "../../deliverables/types";
import { pick, t, texts, useLanguage, type Text } from "../../i18n";
import { SourceError } from "../../project/sources";
import type { ProjectSources } from "../../project/types";
import { SheetViewer } from "../../viewers/sheet/SheetViewer";

export type ClientBoqLoaded = { view: SheetView } | { failed: Text } | null;

/** The client BOQ's read-only view while `live`; `at` (the newest import) changing loads it again. */
export function useClientBoq(sources: ProjectSources, fileId: string, at: string | null, live = true): ClientBoqLoaded {
  const [loaded, setLoaded] = useState<ClientBoqLoaded>(null);
  useEffect(() => {
    if (!live) return;
    let current = true;
    sources.clientBoq(fileId).then(
      (view) => current && setLoaded({ view }),
      (error) => current && setLoaded({ failed: error instanceof SourceError ? error.line : texts.canvasFailed }),
    );
    return () => {
      current = false;
    };
  }, [live, sources, fileId, at]);
  return loaded;
}

export function ClientBoqDoc({ projectId, sources, fileId }: { projectId: string; sources: ProjectSources; fileId: string }) {
  useLanguage();
  // a new import of the file is announced on the live stream
  const [at, setAt] = useState<string | null>(null);
  useEffect(() => {
    const stop = new AbortController();
    sources.activity((event) => {
      if (event.type === "client_boq" && event.client_boq.file_id === fileId) setAt(event.client_boq.at);
    }, stop.signal);
    return () => stop.abort();
  }, [sources, fileId]);
  const loaded = useClientBoq(sources, fileId, at);

  if (loaded && "view" in loaded) return <SheetViewer projectId={projectId} view={loaded.view} mode="workspace" readOnly />;
  return (
    <div className="h-full bg-paper p-3">
      {loaded ? (
        <p role="alert" className="text-copper">
          {pick(loaded.failed)}
        </p>
      ) : (
        <p className="text-slate">{t("clientBoqLoading")}</p>
      )}
    </div>
  );
}

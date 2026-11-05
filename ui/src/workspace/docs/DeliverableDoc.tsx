// A Deliverable as the open document: its kind's viewer in mode "workspace" (the review board without Close or its
// own title, which the workspace shows), or a calm line when ONE has no viewer for its kind yet. Its kind comes from
// the project's documents (DocumentsContext); only one not listed yet (just made, its event still on the way) is
// looked up in the core. A kind that cannot be known says the document could not be opened, never a blank sheet.
import { useContext, useEffect, useState, type Ref } from "react";
import { t, useLanguage } from "../../i18n";
import type { Anchor, DeliverableInfo, ProjectSources, ViewerHandle } from "../../project/types";
import { viewerFor } from "../../viewers/registry";
import { DocumentsContext } from "../documents";

type Kind = DeliverableInfo["kind"];

export function DeliverableDoc(props: {
  projectId: string;
  sources: ProjectSources;
  deliverableId: string;
  ref?: Ref<ViewerHandle>;
  onSelection?(anchor: Anchor | null, label: string | null): void;
}) {
  const { projectId, sources, deliverableId } = props;
  useLanguage();
  const listed = useContext(DocumentsContext)?.deliverables.find((d) => d.id === deliverableId)?.kind;
  // not in the project's list: read from the core once; null when it is not there either (or cannot be read)
  const [read, setRead] = useState<{ id: string; kind: Kind | null }>();
  useEffect(() => {
    if (listed) return;
    let live = true;
    sources.deliverables().then(
      (list) => live && setRead({ id: deliverableId, kind: list.find((d) => d.id === deliverableId)?.kind ?? null }),
      () => live && setRead({ id: deliverableId, kind: null }),
    );
    return () => {
      live = false;
    };
  }, [listed, sources, deliverableId]);
  const kind = listed ?? (read?.id === deliverableId ? read.kind : undefined);

  if (kind === undefined)
    return (
      <div className="h-full bg-paper p-3">
        <p className="text-slate">{t("deliverableLoading")}</p>
      </div>
    );
  if (kind === null)
    return (
      <div className="h-full bg-paper p-3">
        <p role="alert" className="text-copper">
          {t("documentFailed")}
        </p>
      </div>
    );
  const Viewer = viewerFor(kind);
  if (!Viewer)
    return (
      <div className="h-full bg-paper p-3">
        <p className="text-slate">{t("noViewer")}</p>
      </div>
    );
  return <Viewer ref={props.ref} projectId={projectId} deliverableId={deliverableId} mode="workspace" onSelection={props.onSelection} />;
}

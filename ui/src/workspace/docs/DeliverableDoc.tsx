// A Deliverable as the open document: its kind's viewer in mode "workspace" (the review board without Close or its
// own title, which the workspace shows), or a calm line when ONE has no viewer for its kind yet.
import { useEffect, useState, type Ref } from "react";
import { t, useLanguage } from "../../i18n";
import type { Anchor, DeliverableInfo, ProjectSources, ViewerHandle } from "../../project/types";
import { viewerFor } from "../../viewers/registry";

export function DeliverableDoc(props: {
  projectId: string;
  sources: ProjectSources;
  deliverableId: string;
  ref?: Ref<ViewerHandle>;
  onSelection?(anchor: Anchor | null, label: string | null): void;
}) {
  const { projectId, sources, deliverableId } = props;
  useLanguage();
  // its kind, from the project's list; undefined until known, null when the Deliverable is not in it (or the list
  // could not be read)
  const [kind, setKind] = useState<DeliverableInfo["kind"] | null>();
  useEffect(() => {
    let live = true;
    setKind(undefined);
    sources.deliverables().then(
      (list) => live && setKind(list.find((d) => d.id === deliverableId)?.kind ?? null),
      () => live && setKind(null),
    );
    return () => {
      live = false;
    };
  }, [sources, deliverableId]);

  // not known yet, or gone (the workspace then opens Project files): nothing to show
  if (!kind) return <div className="h-full bg-paper" />;
  const Viewer = viewerFor(kind);
  if (!Viewer)
    return (
      <div className="h-full bg-paper p-3">
        <p className="text-slate">{t("noViewer")}</p>
      </div>
    );
  return <Viewer ref={props.ref} projectId={projectId} deliverableId={deliverableId} mode="workspace" onSelection={props.onSelection} />;
}

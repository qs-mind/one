// The open document of the workspace, shown with the viewers ONE has: a Deliverable in its kind's viewer, a client
// BOQ read only, a file's pages, or Project files. The handle's `locate` reaches the Deliverable's viewer; the other
// documents have none and give null.
import { useImperativeHandle, useRef, type Ref } from "react";
import type { Anchor, DocKind, Opened, ProjectSources, ViewerHandle } from "../project/types";
import { ClientBoqDoc } from "./docs/ClientBoqDoc";
import { DeliverableDoc } from "./docs/DeliverableDoc";
import { FileDoc } from "./docs/FileDoc";
import { FilesDoc } from "./docs/FilesDoc";
import { ViewPart } from "../chat/parts/view/ViewPart";
import { viewOf } from "./views";
import { useRowsDocument } from "./rowsDocuments";
import { ApprovalCard } from "../chat/parts/ApprovalCard";

export function DocumentView(props: {
  projectId: string;
  sources: ProjectSources;
  opened: Opened;
  ref?: Ref<ViewerHandle>;
  onSelection?(anchor: Anchor | null, label: string | null): void;
  /** A line about the opening (a source whose place could not be shown): a file says it under its controls. */
  notice?: string | null;
}) {
  const { projectId, sources, opened } = props;
  const viewer = useRef<ViewerHandle>(null);
  useImperativeHandle(props.ref, () => ({ locate: (anchor, options) => viewer.current?.locate(anchor, options) ?? null }), []);

  const at = opened.key.indexOf(":");
  const kind = opened.key.slice(0, at) as DocKind;
  const id = opened.key.slice(at + 1);
  const rows = useRowsDocument(kind === "view" ? id : "");
  // each document starts fresh: its own scroll, page and selection
  switch (kind) {
    case "deliverable":
      return (
        <DeliverableDoc key={opened.key} ref={viewer} projectId={projectId} sources={sources} deliverableId={id} onSelection={props.onSelection} />
      );
    case "clientboq":
      return <ClientBoqDoc key={opened.key} projectId={projectId} sources={sources} fileId={id} />;
    case "file":
      return <FileDoc key={opened.key} projectId={projectId} sources={sources} fileId={id} opened={opened} notice={props.notice} />;
    case "files":
      return <FilesDoc />;
    case "view": {
      if (rows) return <div className="h-full overflow-auto p-4"><ApprovalCard {...rows} inDocument /></div>;
      // a view the Lead QS showed, wider than the chat: here at the document's width
      const view = viewOf(id);
      return view ? (
        <div key={opened.key} className="h-full overflow-auto p-4">
          <ViewPart view={view} projectId={projectId} whole />
        </div>
      ) : null;
    }
  }
}

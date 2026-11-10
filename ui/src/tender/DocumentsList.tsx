// "Documents" in the side column (S144: what there is to open): the tender's Deliverables, the Project Map and the
// Project files, each opening in the document's place beside a narrow thread. A file opens from Project files, or
// from a source in the thread.
import { FileSpreadsheetIcon, FolderIcon, MapIcon } from "lucide-react";
import { Link } from "react-router";
import { paths } from "@/app/paths";
import { ListRow } from "@/design/ListRow";
import { SectionLabel } from "@/design/SectionLabel";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";
import type { Documents } from "@/workspace/documents";

export const MAP_DOC = "view:project-map";
export const FILES_DOC = "files:all";

export function DocumentsList({ projectId, docs }: { projectId: string; docs: Documents | null }) {
  const t = useText();
  const rows = [
    ...(docs?.deliverables ?? []).map((d) => ({ doc: `deliverable:${d.id}`, title: d.title, icon: FileSpreadsheetIcon })),
    { doc: MAP_DOC, title: t(texts.projectMap), icon: MapIcon },
    { doc: FILES_DOC, title: t(texts.projectFiles), icon: FolderIcon },
  ];
  return (
    <section aria-labelledby="tender-documents" className="flex flex-col gap-3">
      <SectionLabel id="tender-documents">{t(texts.documentsTitle)}</SectionLabel>
      <ul className="flex flex-col">
        {rows.map(({ doc, title, icon: Icon }) => (
          <li key={doc} data-doc={doc}>
            <ListRow
              render={<Link to={paths.doc(projectId, doc)} />}
              frame="plain"
              leading={<Icon aria-hidden className="size-4" />}
              title={<bdi dir={textDir(title)}>{title}</bdi>}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

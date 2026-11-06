// ONE's own ids (a file's, a document's, an import's: 32 hex letters, uuid4().hex) never reach the engineer. In what
// the Lead QS writes, an id of a document this project has reads as that document's name; any other id goes, with the
// words that only introduced it («المعرف:», "Import ID:"). An id cut short with «…» goes too.
import { useContext } from "react";
import { DocumentsContext } from "../workspace/documents";

const LEAD = String.raw`(?:(?:import|document|file|deliverable)\s+)?\bid\b\s*[:：]?\s*|\(?(?:المعرف|معرف|رقم الاستيراد)\)?\s*[:：]?\s*`;
const HEX = String.raw`(?<![0-9a-z])(?:[0-9a-f]{32}(?![0-9a-z])|(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{6,31}(?:…|\.\.\.))`;
const PATTERN = new RegExp(`([\`"«(]?)(${LEAD})?([\`"«(]?)(${HEX})([\`"»)]?)`, "gi");

/** `text` with each id read as its document's name (from `names`), or taken out. */
export function withoutIds(text: string, names: ReadonlyMap<string, string>): string {
  if (!/[0-9a-f]{6}/i.test(text)) return text;
  return text
    .replace(PATTERN, (_all, outer: string, lead: string | undefined, open: string, id: string, close: string) => {
      const name = names.get(id.toLowerCase());
      if (!name) return "";
      return lead ? `${open}${name}${open ? close : ""}` : `${outer}${open}${name}${close}`; // «المعرف:» goes with it
    })
    .replace(/[ \t]{2,}/g, " ")
    .replace(/[ \t]+([.,،؛:)])/g, "$1");
}

/** The names of the open project's documents by their ids: files, client BOQs and Deliverables. */
export function useDocumentNames(): ReadonlyMap<string, string> {
  const docs = useContext(DocumentsContext);
  const names = new Map<string, string>();
  for (const file of docs?.files ?? []) names.set(file.id, file.name);
  for (const boq of docs?.clientBoqs ?? []) names.set(boq.file_id, boq.name);
  for (const deliverable of docs?.deliverables ?? []) names.set(deliverable.id, deliverable.title);
  return names;
}

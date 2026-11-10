// Placeholder: U5 replaces it with the tender place. One component serves the tender's four addresses: the
// conversation, a document (docId), the team room and a member's card (memberId).
import { useLocation, useParams } from "react-router";
import { app } from "@/texts/app";
import { useText } from "@/texts/useText";

export type TenderView = "conversation" | "doc" | "room" | "member";

export function Tender() {
  const t = useText();
  const { id, docId, memberId } = useParams();
  const end = useLocation().pathname.split("/")[3];
  const view: TenderView = end === "doc" || end === "room" || end === "member" ? end : "conversation";
  return (
    <main data-place="tender" data-tender={id} data-view={view} data-doc={docId} data-member={memberId} className="p-12">
      <h1 className="text-3xl font-bold">{t(app.tender)}</h1>
    </main>
  );
}

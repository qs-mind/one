// Placeholder: U4 replaces it with Home (docs/plans/2026-11-09-phase-1-agentic-tender-office.md, U4).
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";

export function Home() {
  const t = useText();
  return (
    <main data-place="home" className="p-12">
      <h1 className="text-3xl font-bold">{t(common.home)}</h1>
    </main>
  );
}

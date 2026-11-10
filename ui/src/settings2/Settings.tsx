// Placeholder: U8 replaces it with Settings, one section at a time (/settings/:section).
import { useParams } from "react-router";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";

export function Settings() {
  const t = useText();
  const { section } = useParams();
  return (
    <main data-place="settings" data-section={section} className="p-12">
      <h1 className="text-3xl font-bold">{t(common.settings)}</h1>
    </main>
  );
}

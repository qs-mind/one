import { HouseIcon, LayersIcon, SettingsIcon } from "lucide-react";
import { useState } from "react";
import { Rail } from "@/design/Rail";
import { common } from "@/texts/common";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function RailDemo() {
  const t = useText();
  const [current, setCurrent] = useState("home");
  const item = (id: string, label: string, icon: typeof HouseIcon) => ({
    id,
    label,
    icon,
    current: current === id,
    onSelect: () => setCurrent(id),
  });
  return (
    <Demo id="rail" title="Rail">
      <State name={t(common.navigation)} className="flex h-120 flex-col gap-2">
        <div className="flex flex-1">
          <Rail
            label={t(common.navigation)}
            items={[item("home", t(common.home), HouseIcon), item("tenders", t(common.tenders), LayersIcon)]}
            footerItems={[item("settings", t(common.settings), SettingsIcon)]}
          />
        </div>
      </State>
    </Demo>
  );
}

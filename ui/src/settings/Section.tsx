// The settings of one of the core's four sections (ai, caps, privacy, look), in the registry's order, each drawn
// from its data. `after` places a section's own part under one setting (the models per role under `ai.models`).
import { Fragment, type ReactNode } from "react";
import { type Change, SettingField } from "./Field";
import type { Setting } from "./useSettings";

type SectionProps = {
  section: Setting["section"];
  settings: Setting[];
  change: Change;
  after?: (setting: Setting) => ReactNode;
};

export function SettingsSection({ section, settings, change, after }: SectionProps) {
  return (
    <div className="flex flex-col gap-10">
      {settings
        .filter((setting) => setting.section === section)
        .map((setting) => (
          <Fragment key={setting.key}>
            <SettingField setting={setting} change={change} />
            {after?.(setting)}
          </Fragment>
        ))}
    </div>
  );
}

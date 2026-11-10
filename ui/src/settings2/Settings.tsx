// Settings: the eight sections in a list at the start side, the open one beside it (/settings/:section). Four
// sections hold the core's settings (GET /settings, drawn from data); the others have their own routes. Every
// change saves by itself; nothing here has a Save button.
import type { ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router";
import { ListRow } from "@/design/ListRow";
import { Button } from "@/design/ui/button";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import { AiSection } from "./AiSection";
import { Backup } from "./Backup";
import { Connectors } from "./Connectors";
import { MyProfile } from "./MyProfile";
import { Privacy } from "./Privacy";
import { SettingsSection } from "./Section";
import { Spent } from "./Spent";
import { Team } from "./Team";
import { useSettings } from "./useSettings";

/** The sections in the order the list shows them; the first is the one the rail opens (paths.FIRST_SETTINGS). */
export const SECTIONS = ["me", "ai", "team", "caps", "connectors", "backup", "privacy", "look"] as const;
type SectionId = (typeof SECTIONS)[number];
const isSection = (id: string | undefined): id is SectionId => (SECTIONS as readonly (string | undefined)[]).includes(id);

const LEADS: Record<SectionId, TextPair> = {
  me: texts.meLead,
  ai: texts.savesItself,
  team: texts.teamLead,
  caps: texts.savesItself,
  connectors: texts.connectorsLead,
  backup: texts.backupLead,
  privacy: texts.privacyLead,
  look: texts.savesItself,
};

export function Settings() {
  const t = useText();
  const { section } = useParams();
  const { loaded, load, change } = useSettings();
  if (!isSection(section)) return <Navigate to={`../${SECTIONS[0]}`} relative="path" replace />;

  // The core's settings, or a line while they load or when they could not.
  const fromCore = (body: (settings: Parameters<typeof SettingsSection>[0]["settings"]) => ReactNode) =>
    loaded.state === "ready" ? (
      body(loaded.settings)
    ) : loaded.state === "loading" ? (
      <div aria-busy="true" className="min-h-14" />
    ) : (
      <div className="flex flex-wrap items-center gap-4">
        <p className="text-xs font-bold">{t(texts.notLoaded)}</p>
        <Button variant="outline" onClick={() => void load()}>
          {t(texts.tryAgain)}
        </Button>
      </div>
    );

  const bodies: Record<SectionId, () => ReactNode> = {
    me: () => <MyProfile />,
    ai: () => fromCore((settings) => <AiSection settings={settings} change={change} />),
    team: () => <Team />,
    caps: () => (
      <>
        {fromCore((settings) => <SettingsSection section="caps" settings={settings} change={change} />)}
        <Spent />
      </>
    ),
    connectors: () => <Connectors />,
    backup: () => <Backup />,
    privacy: () => (
      <>
        <Privacy />
        {fromCore((settings) => <SettingsSection section="privacy" settings={settings} change={change} />)}
      </>
    ),
    look: () => fromCore((settings) => <SettingsSection section="look" settings={settings} change={change} />),
  };

  return (
    <main data-place="settings" data-section={section} className="flex min-h-full flex-wrap gap-x-4 px-4">
      <nav aria-label={t(texts.sections)} className="flex max-w-70 flex-[1_1_13.75rem] flex-col gap-1 pt-18 pb-8">
        {SECTIONS.map((id) => (
          <ListRow
            key={id}
            render={<Link to={`../${id}`} relative="path" aria-current={id === section ? "page" : undefined} />}
            current={id === section}
            tone={id === section ? "default" : "muted"}
            title={t(texts[id])}
            className="mx-0 px-4"
          />
        ))}
      </nav>
      <div className="flex max-w-190 min-w-0 flex-[999_1_32.5rem] flex-col gap-10 px-10 pt-18 pb-12 max-sm:px-0">
        <header className="flex flex-col gap-2">
          <h1 className="text-2xl font-bold">{t(texts[section])}</h1>
          <p className="text-muted-foreground">{t(LEADS[section])}</p>
        </header>
        {bodies[section]()}
      </div>
    </main>
  );
}

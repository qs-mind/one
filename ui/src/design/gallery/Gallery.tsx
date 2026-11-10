// The design gallery (dev only, /fake.html): a top bar with three switches (page, language, theme), then either
// every component in every state, or the specimens. The switches write the address; the app's own live in Settings.
import type { ReactNode } from "react";
import { ConversationGallery } from "@/conversation/gallery/ConversationGallery";
import { Pill } from "@/design/Pill";
import { Wordmark } from "@/design/Wordmark";
import { Button } from "@/design/ui/button";
import { common } from "@/texts/common";
import { conversationGallery } from "@/texts/design/conversation";
import { foundation } from "@/texts/design/foundation";
import { text, useText } from "@/texts/useText";
import type { TextPair } from "@/texts/types";
import { useAddress, type Address } from "./address";
import { ControlsSection } from "./ControlsSection";
import { FoundationSection } from "./FoundationSection";
import { Specimens } from "./Specimens";
import { SurfacesSection } from "./SurfacesSection";

type Option<K extends keyof Address> = { value: Address[K]; label: ReactNode };

function Switch<K extends keyof Address>(props: {
  name: TextPair;
  part: K;
  options: readonly Option<K>[];
  address: Address;
  go: (next: Partial<Address>) => void;
}) {
  const t = useText();
  const { name, part, options, address, go } = props;
  return (
    <div role="group" aria-label={t(name)} className="flex flex-wrap items-center gap-2">
      {options.map((option) => (
        <Button
          key={option.value}
          variant="outline"
          aria-pressed={address[part] === option.value}
          className="aria-pressed:border-transparent aria-pressed:bg-muted aria-pressed:font-bold hover:aria-pressed:bg-muted-hover"
          onClick={() => go({ [part]: option.value } as Partial<Address>)}
        >
          {option.label}
        </Button>
      ))}
    </div>
  );
}

function Section({ id, title, children }: { id: string; title: TextPair; children: ReactNode }) {
  const t = useText();
  return (
    <section aria-labelledby={`section-${id}`} className="flex flex-col gap-8">
      <h2 id={`section-${id}`} className="text-2xl font-bold">
        {t(title)}
      </h2>
      {children}
    </section>
  );
}

export function Gallery() {
  const t = useText();
  const [address, go] = useAddress();
  return (
    <div className="min-h-dvh">
      <header className="flex flex-wrap items-center gap-x-8 gap-y-3 border-b border-border px-(--gutter) py-4">
        <Wordmark />
        <nav aria-label={t(foundation.switches)} className="flex flex-wrap items-center gap-x-8 gap-y-3">
          <Switch
            name={foundation.page}
            part="view"
            address={address}
            go={go}
            options={[
              { value: "gallery", label: t(foundation.viewGallery) },
              { value: "specimens", label: t(foundation.viewSpecimens) },
              { value: "conversation", label: t(conversationGallery.view) },
            ]}
          />
          <Switch
            name={foundation.language}
            part="lang"
            address={address}
            go={go}
            options={[
              { value: "ar", label: <span lang="ar">{text(foundation.arabic, "ar")}</span> },
              { value: "en", label: <span lang="en">{text(foundation.english, "en")}</span> },
            ]}
          />
          <Switch
            name={foundation.theme}
            part="theme"
            address={address}
            go={go}
            options={[
              { value: "system", label: t(foundation.themeSystem) },
              { value: "light", label: t(foundation.themeLight) },
              { value: "dark", label: t(foundation.themeDark) },
            ]}
          />
        </nav>
      </header>
      {/* Remounted per language, so sample values typed into fields come back in the new language. */}
      <main key={address.lang} className="mx-auto flex max-w-300 flex-col gap-18 px-(--gutter) pt-10 pb-18">
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-3xl font-bold max-sm:text-2xl">{t(foundation.title)}</h1>
            <Pill>{t(common.sample)}</Pill>
          </div>
          <p className="max-w-155 text-lg text-muted-foreground">{t(foundation.intro)}</p>
        </div>
        {address.view === "conversation" ? (
          <ConversationGallery />
        ) : address.view === "specimens" ? (
          <Specimens />
        ) : (
          <>
            <Section id="foundation" title={foundation.sectionFoundation}>
              <FoundationSection />
            </Section>
            <Section id="controls" title={foundation.sectionControls}>
              <ControlsSection />
            </Section>
            <Section id="surfaces" title={foundation.sectionSurfaces}>
              <SurfacesSection />
            </Section>
          </>
        )}
      </main>
    </div>
  );
}

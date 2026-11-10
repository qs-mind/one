// The specimens: four regions of the approved mockups rebuilt from the real components, each under its sample label.
import type { ReactNode } from "react";
import { Pill } from "@/design/Pill";
import { common } from "@/texts/common";
import { specimens } from "@/texts/design/specimens";
import { useText } from "@/texts/useText";
import type { TextPair } from "@/texts/types";
import { ConversationSlice } from "./specimens/ConversationSlice";
import { MessageBox } from "./specimens/MessageBox";
import { MixedSlice } from "./specimens/MixedSlice";
import { TenderSide } from "./specimens/TenderSide";

function Specimen({ id, title, children }: { id: string; title: TextPair; children: ReactNode }) {
  const t = useText();
  return (
    <section data-specimen={id} aria-labelledby={`specimen-${id}`} className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={`specimen-${id}`} className="text-xl font-bold">
          {t(title)}
        </h2>
        <Pill>{t(common.sample)}</Pill>
      </div>
      {children}
    </section>
  );
}

export function Specimens() {
  const t = useText();
  return (
    <div className="flex flex-col gap-18">
      <p className="max-w-155 text-lg text-muted-foreground">{t(specimens.intro)}</p>
      <Specimen id="tender-side" title={specimens.tenderSide}>
        <TenderSide />
      </Specimen>
      <Specimen id="conversation" title={specimens.conversation}>
        <ConversationSlice />
      </Specimen>
      <Specimen id="message-box" title={specimens.messageBox}>
        <MessageBox />
      </Specimen>
      <Specimen id="mixed" title={specimens.mixed}>
        <MixedSlice />
      </Specimen>
    </div>
  );
}

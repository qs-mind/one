// Home's one message box (U3's Composer), the Home conversation above it, and why the Lead cannot work now. A drop
// on the box is a tender: a dropped folder becomes a new tender, which opens at once while its files go in. Loose
// files are not a tender: the box says to drop the whole folder.
import { type DragEvent, type Ref, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { client, type Schemas } from "@/api/client";
import { Composer } from "@/conversation/Composer";
import { Thread } from "@/conversation/Thread";
import { buttonVariants } from "@/design/ui/button";
import { paths } from "@/app/paths";
import { home } from "@/texts/home";
import { useText } from "@/texts/useText";
import { dropTender, folderOf } from "./folderDrop";
import { useHomeChat } from "./homeChat";

const FIX_SECTION: Partial<Record<NonNullable<Schemas["LeadBlock"]["fix"]>, { section: string; words: Schemas["Text"] }>> = {
  ai: { section: "ai", words: home.openAi },
  consent: { section: "ai", words: home.openAi },
  search: { section: "ai", words: home.openAi },
  caps: { section: "caps", words: home.openCaps },
};

function Blocked({ block }: { block: Schemas["LeadBlock"] }) {
  const t = useText();
  const fix = block.fix ? FIX_SECTION[block.fix] : undefined;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <p className="text-xs text-muted-foreground">{t(block.reason)}</p>
      {fix && (
        <Link className={buttonVariants({ variant: "outline" })} to={paths.settings(fix.section)}>
          {t(fix.words)}
        </Link>
      )}
    </div>
  );
}

function useLeadName(): string {
  const t = useText();
  const [title, setTitle] = useState<Schemas["Text"]>();
  useEffect(() => {
    let live = true;
    client
      .GET("/team/members")
      .then(({ data }) => live && setTitle(data?.members.find((member) => member.role === "lead")?.title))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);
  return title ? t(title) : "";
}

const holdsFiles = (event: DragEvent) => event.dataTransfer?.types?.includes("Files") ?? false;

/** Lets the box drop its drag state when the drop was taken here before it saw it. */
const leave = (target: EventTarget) => target instanceof Element && target.closest("form")?.dispatchEvent(new Event("dragleave", { bubbles: true }));

type HomeBoxProps = {
  blocked: Schemas["LeadBlock"] | null;
  /** The Home conversation, for a waiting item to bring into view. */
  conversationRef?: Ref<HTMLElement>;
};

export function HomeBox({ blocked, conversationRef }: HomeBoxProps) {
  const t = useText();
  const navigate = useNavigate();
  const chat = useHomeChat();
  const leadName = useLeadName();
  const [line, setLine] = useState<Schemas["Text"]>();

  function onDrop(event: DragEvent<HTMLDivElement>) {
    if (!holdsFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    leave(event.target);
    const entries = folderOf(event.dataTransfer);
    if (!entries) return setLine(home.folderOnly);
    setLine(undefined);
    void dropTender(entries, (id) => navigate(paths.tender(id))).then((refused) => refused && setLine(refused));
  }

  return (
    <div className="flex flex-col gap-4">
      {chat.messages.length > 0 && (
        <section ref={conversationRef} aria-label={t(home.conversationLabel)} tabIndex={-1} className="flex flex-col">
          <Thread
            messages={chat.messages}
            leadName={leadName}
            plan={null}
            findings={[]}
            onApprovePlan={() => undefined}
            onDiscussPlan={() => undefined}
            onPlanChange={() => undefined}
            onDecide={() => undefined}
          />
        </section>
      )}
      {blocked && <Blocked block={blocked} />}
      <div onDropCapture={onDrop}>
        <Composer
          onSend={chat.send}
          onSteer={chat.steer}
          activity={chat.activity}
          disabled={blocked !== null}
          placeholder={t(home.placeholder)}
        />
      </div>
      {line && (
        <p role="status" className="text-xs text-muted-foreground">
          {t(line)}
        </p>
      )}
    </div>
  );
}

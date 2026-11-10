// The thin column that switches between places (Home, Tenders, Settings). The first Tab stop, on the start side.
// U2 passes its router links through `render`; without one an item is a button.
import type { LucideIcon } from "lucide-react";
import type { ReactElement } from "react";
import { Wordmark } from "@/design/Wordmark";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/design/ui/tooltip";

export type RailItem = {
  id: string;
  label: string;
  icon: LucideIcon;
  current?: boolean;
  render?: ReactElement;
  onSelect?: () => void;
};

type RailProps = { label: string; items: readonly RailItem[]; footerItems?: readonly RailItem[] };

const ITEM =
  "inline-flex size-12 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-accent hover:text-foreground aria-[current=page]:bg-background aria-[current=page]:text-foreground max-sm:size-11";

function RailButton({ item }: { item: RailItem }) {
  const Icon = item.icon;
  // Base UI merges these into the rendered element: the link's own handlers and attributes stay.
  return (
    <Tooltip>
      <TooltipTrigger
        delay={200}
        render={item.render ?? <button type="button" />}
        className={ITEM}
        aria-label={item.label}
        aria-current={item.current ? "page" : undefined}
        onClick={item.onSelect}
      >
        <Icon aria-hidden className="size-5.5" strokeWidth={1.6} />
      </TooltipTrigger>
      <TooltipContent side="inline-end">{item.label}</TooltipContent>
    </Tooltip>
  );
}

export function Rail({ label, items, footerItems = [] }: RailProps) {
  return (
    <nav aria-label={label} className="flex w-(--rail-w) shrink-0 flex-col items-center gap-3 bg-muted py-6 max-sm:w-14">
      <Wordmark className="mb-2" />
      {items.map((item) => (
        <RailButton key={item.id} item={item} />
      ))}
      <span aria-hidden className="flex-1" />
      {footerItems.map((item) => (
        <RailButton key={item.id} item={item} />
      ))}
    </nav>
  );
}

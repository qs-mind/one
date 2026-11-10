// The one row of the interface: a stage, a member, a tender, a waiting item, a settings section, an option.
// `render` makes it a link, a button or a label; every inner part is a <span>, so the row is valid as any of them.
import { useRender } from "@base-ui/react/use-render";
import { isValidElement, type ReactElement, type ReactNode } from "react";
import { cn } from "@/design/lib/utils";

type Frame = "plain" | "divided" | "boxed" | "panel";

type ListRowProps = {
  render?: ReactElement; // <a href>, <button type="button">, <label>; default <div>. Interactive when given.
  frame?: Frame;
  size?: "default" | "lg"; // title 17 | 19 bold
  tone?: "default" | "strong" | "muted"; // title 400 | title 700 | the whole row muted
  current?: boolean; // the selected option or the current section
  leading?: ReactNode;
  title: ReactNode;
  meta?: ReactNode; // second line, 15 muted
  detail?: ReactNode; // third line, 15 foreground
  trailing?: ReactNode;
  className?: string;
};

const FRAME: Record<Frame, string> = {
  plain: "-mx-3 min-h-11 gap-3 rounded-lg px-3",
  divided:
    "relative -mx-4 flex-wrap gap-6 rounded-xl px-4 py-5 after:absolute after:inset-x-4 after:bottom-0 after:h-px after:bg-border last:after:hidden",
  boxed: "min-h-14 gap-4 rounded-xl border border-border px-5 py-3",
  panel: "flex-wrap gap-4 rounded-2xl bg-muted px-5 py-4",
};

const BODY: Record<Frame, string> = {
  plain: "flex-1",
  boxed: "flex-1",
  divided: "flex-[1_1_15rem]",
  panel: "flex-[1_1_15rem]",
};

export function ListRow({
  render,
  frame = "plain",
  size = "default",
  tone = "default",
  current = false,
  leading,
  title,
  meta,
  detail,
  trailing,
  className,
}: ListRowProps) {
  const interactive = render !== undefined;
  const isLabel = isValidElement(render) && render.type === "label";
  const showsCurrent = current && (frame === "plain" || frame === "boxed");
  const filled = frame === "panel" || showsCurrent;
  const muted = tone === "muted";
  // Rule R2: secondary text on a filled ground turns foreground while that ground is hovered.
  const hoverText = interactive && filled ? "group-hover/row:text-foreground" : "";

  const rootClass = cn(
    "group/row flex min-w-0 items-center text-start",
    FRAME[frame],
    frame === "plain" && meta !== undefined && "py-2",
    showsCurrent && "bg-muted text-foreground",
    showsCurrent && frame === "boxed" && "border-transparent",
    muted && !showsCurrent && "text-muted-foreground",
    muted && hoverText,
    interactive && (filled ? "hover:bg-muted-hover" : "hover:bg-accent"),
    interactive && (isLabel ? "focus-ring-within" : "focus-inset"),
    // A label row whose radio or checkbox is off reads as off: the whole row turns muted (1.4).
    isLabel && "has-data-disabled:text-muted-foreground",
    className,
  );

  const bold = size === "lg" || tone === "strong" || showsCurrent;
  const children = (
    <>
      {leading !== undefined && (
        <>
          <span className="flex shrink-0 items-center">{leading}</span>{" "}
        </>
      )}
      <span className={cn("flex min-w-0 flex-col", BODY[frame])}>
        <span className={cn(size === "lg" ? "text-lg" : "text-base", bold && "font-bold")}>{title}</span>
        {meta !== undefined && (
          <>
            {" "}
            <span className={cn("text-xs text-muted-foreground", hoverText)}>{meta}</span>
          </>
        )}
        {detail !== undefined && (
          <>
            {" "}
            <span className={cn("text-xs", muted ? "text-muted-foreground" : "text-foreground", muted && hoverText)}>
              {detail}
            </span>
          </>
        )}
      </span>
      {trailing !== undefined && (
        <>
          {" "}
          <span className={cn("ms-auto flex shrink-0 items-center gap-6 text-xs text-muted-foreground", hoverText)}>
            {trailing}
          </span>
        </>
      )}
    </>
  );

  return useRender({ defaultTagName: "div", render, props: { className: rootClass, children } });
}

// ai-elements `message`, trimmed for ONE: Message, MessageContent, MessageResponse, MessageActions and MessageAction
// (the "actions" part). Branches, toolbar and attachments are dropped (ONE has none); Streamdown draws the reply with
// ONE's own type, no code or table controls, no link modal, and the direction ONE chooses, never "auto".
import type { UIMessage } from "ai";
import type { ComponentProps, HTMLAttributes } from "react";
import { memo } from "react";
import { Streamdown, type Components } from "streamdown";
import { cn } from "@/design/lib/utils";
import { Button } from "@/design/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/design/ui/tooltip";

export type MessageProps = HTMLAttributes<HTMLDivElement> & {
  from: UIMessage["role"];
};

export const Message = ({ className, from, ...props }: MessageProps) => (
  <div
    data-from={from}
    className={cn(
      "group flex w-full flex-col gap-2",
      from === "user" ? "is-user max-w-[78%] self-end" : "is-assistant",
      className,
    )}
    {...props}
  />
);

export type MessageContentProps = HTMLAttributes<HTMLDivElement>;

export const MessageContent = ({ children, className, ...props }: MessageContentProps) => (
  <div
    className={cn(
      "flex w-fit max-w-full min-w-0 flex-col gap-2 text-base text-foreground",
      "group-[.is-user]:ms-auto group-[.is-user]:rounded-2xl group-[.is-user]:bg-muted group-[.is-user]:px-5 group-[.is-user]:py-3",
      className,
    )}
    {...props}
  >
    {children}
  </div>
);

export type MessageActionsProps = ComponentProps<"div">;

export const MessageActions = ({ className, children, ...props }: MessageActionsProps) => (
  <div className={cn("flex items-center gap-1", className)} {...props}>
    {children}
  </div>
);

export type MessageActionProps = ComponentProps<typeof Button> & {
  /** The words of the action: its tooltip and its accessible name. */
  label: string;
};

export const MessageAction = ({ label, children, variant = "ghost", size = "icon", ...props }: MessageActionProps) => (
  <Tooltip>
    <TooltipTrigger
      render={
        <Button aria-label={label} size={size} type="button" variant={variant} {...props}>
          {children}
        </Button>
      }
    />
    <TooltipContent>{label}</TooltipContent>
  </Tooltip>
);

/** Streamdown hands each element its hast node; it must not reach the DOM. */
function drop<P extends { node?: unknown }>(props: P): Omit<P, "node"> {
  const { node, ...rest } = props;
  void node;
  return rest;
}

const components: Components = {
  p: (props) => <p {...drop(props)} />,
  a: ({ className, ...props }) => <a className={cn("link", className)} {...drop(props)} />,
  strong: ({ className, ...props }) => <strong className={cn("font-bold", className)} {...drop(props)} />,
  h1: ({ className, ...props }) => <h3 className={cn("text-lg font-bold", className)} {...drop(props)} />,
  h2: ({ className, ...props }) => <h3 className={cn("text-lg font-bold", className)} {...drop(props)} />,
  h3: ({ className, ...props }) => <h3 className={cn("font-bold", className)} {...drop(props)} />,
  ul: ({ className, ...props }) => <ul className={cn("flex list-disc flex-col gap-1 ps-6", className)} {...drop(props)} />,
  ol: ({ className, ...props }) => (
    <ol className={cn("flex list-decimal flex-col gap-1 ps-6", className)} {...drop(props)} />
  ),
  li: (props) => <li {...drop(props)} />,
  table: ({ className, ...props }) => (
    <div className="overflow-x-auto rounded-xl border border-line">
      <table className={cn("w-full border-collapse text-start", className)} {...drop(props)} />
    </div>
  ),
  th: ({ className, ...props }) => (
    <th className={cn("border-b border-border px-3 py-2 text-start font-bold", className)} {...drop(props)} />
  ),
  td: ({ className, ...props }) => (
    <td className={cn("border-b border-row-line px-3 py-2 text-start", className)} {...drop(props)} />
  ),
};

export type MessageResponseProps = {
  children: string;
  /** The reply's direction, from its own letters (ONE never lets the browser guess). */
  dir: "ltr" | "rtl";
  /** True while the reply still streams: unfinished Markdown is closed as it comes. */
  streaming?: boolean;
  className?: string;
};

export const MessageResponse = memo(
  ({ children, dir, streaming = false, className }: MessageResponseProps) => (
    <Streamdown
      className={cn("flex size-full flex-col gap-2", className)}
      components={components}
      controls={false}
      dir={dir}
      linkSafety={{ enabled: false }}
      mode={streaming ? "streaming" : "static"}
    >
      {children}
    </Streamdown>
  ),
  (prev, next) => prev.children === next.children && prev.dir === next.dir && prev.streaming === next.streaming,
);

MessageResponse.displayName = "MessageResponse";

// ai-elements `prompt-input`, trimmed to what ONE's message box needs: a form that takes dropped or pasted files AND
// folders, a textarea that sends on Enter (Shift+Enter breaks a line, never while an input method composes), and a
// send button. The input-group, menus, select, hover card, tabs, command and speech parts are dropped; the look is
// the message box of section 4.26 (U1's Textarea "bare" and Button "icon"). Files stay File objects: ONE uploads
// them itself, so nothing is turned into a data URL.
import {
  type ClipboardEventHandler,
  type ComponentProps,
  createContext,
  type DragEvent,
  type FormEvent,
  type KeyboardEventHandler,
  type ReactNode,
  useCallback,
  useContext,
  useMemo,
  useState,
} from "react";
import { cn } from "@/design/lib/utils";
import { Button } from "@/design/ui/button";
import { Textarea } from "@/design/ui/textarea";

/** A dropped file, or a dropped folder (the core reads a folder itself; the screen only knows its name). */
/** A dropped file, or a folder with its entry, to read its files from. */
export type PromptInputAttachment = { id: string; name: string; kind: "file" | "folder"; file?: File; entry?: FileSystemEntry };

export type PromptInputMessage = { text: string; attachments: PromptInputAttachment[] };

type AttachmentsContext = {
  attachments: PromptInputAttachment[];
  add: (items: Omit<PromptInputAttachment, "id">[]) => void;
  remove: (id: string) => void;
  dragging: boolean;
};

const Attachments = createContext<AttachmentsContext | null>(null);

export const usePromptInputAttachments = () => {
  const context = useContext(Attachments);
  if (!context) throw new Error("usePromptInputAttachments must be used within PromptInput");
  return context;
};

const hasFiles = (event: DragEvent) => event.dataTransfer?.types?.includes("Files") ?? false;

/** What a drop holds: each item as a file or a folder. Without the entry API every item counts as a file. */
export function droppedItems(transfer: DataTransfer): Omit<PromptInputAttachment, "id">[] {
  const items = [...(transfer.items ?? [])].filter((item) => item.kind === "file");
  if (items.length === 0) return [...(transfer.files ?? [])].map((file) => ({ name: file.name, kind: "file", file }));
  return items.flatMap((item): Omit<PromptInputAttachment, "id">[] => {
    const entry = item.webkitGetAsEntry?.();
    if (entry?.isDirectory) return [{ name: entry.name, kind: "folder", entry }];
    const file = item.getAsFile();
    return file ? [{ name: file.name, kind: "file", file }] : [];
  });
}

export type PromptInputProps = Omit<ComponentProps<"form">, "onSubmit"> & {
  onSubmit: (message: PromptInputMessage, event: FormEvent<HTMLFormElement>) => void;
  /** Above the line of the field and the button, inside the box: the dropped items. */
  header?: ReactNode;
};

export const PromptInput = ({ className, onSubmit, header, children, ...props }: PromptInputProps) => {
  const [attachments, setAttachments] = useState<PromptInputAttachment[]>([]);
  const [dragging, setDragging] = useState(false);

  const add = useCallback((items: Omit<PromptInputAttachment, "id">[]) => {
    setAttachments((prev) => [...prev, ...items.map((item) => ({ ...item, id: crypto.randomUUID() }))]);
  }, []);
  const remove = useCallback((id: string) => setAttachments((prev) => prev.filter((it) => it.id !== id)), []);
  const context = useMemo(() => ({ attachments, add, remove, dragging }), [attachments, add, remove, dragging]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const text = String(new FormData(form).get("message") ?? "").trim();
    if (!text && attachments.length === 0) return;
    onSubmit({ text, attachments }, event);
    const field = form.elements.namedItem("message");
    if (field instanceof HTMLTextAreaElement) {
      field.value = "";
      // Where the field grows by script (no field-sizing), it shrinks back on this event.
      field.dispatchEvent(new Event("input", { bubbles: true }));
    }
    setAttachments([]);
  };

  return (
    <Attachments.Provider value={context}>
      <form
        data-drop-target={dragging || undefined}
        className={cn(
          "focus-ring-within flex flex-col gap-2 rounded-2xl border border-input bg-card py-2 ps-5 pe-2",
          "data-drop-target:border-2 data-drop-target:border-foreground data-drop-target:py-[calc(--spacing(2)-1px)] data-drop-target:ps-[calc(--spacing(5)-1px)] data-drop-target:pe-[calc(--spacing(2)-1px)]",
          className,
        )}
        onDragOver={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={(event) => {
          // Leaving for a child of the box is not leaving the box.
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false);
        }}
        onDrop={(event) => {
          if (!hasFiles(event)) return;
          event.preventDefault();
          setDragging(false);
          add(droppedItems(event.dataTransfer));
        }}
        onSubmit={handleSubmit}
        {...props}
      >
        {header}
        <div className="flex items-end gap-3">{children}</div>
      </form>
    </Attachments.Provider>
  );
};

export type PromptInputTextareaProps = ComponentProps<typeof Textarea> & {
  /** Shown while files are dragged over the box. */
  dropPlaceholder?: string;
};

export const PromptInputTextarea = ({ className, placeholder, dropPlaceholder, ...props }: PromptInputTextareaProps) => {
  const { attachments, add, remove, dragging } = usePromptInputAttachments();
  const [composing, setComposing] = useState(false);

  const handleKeyDown: KeyboardEventHandler<HTMLTextAreaElement> = (event) => {
    if (event.key === "Enter" && !event.shiftKey && !composing && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const submit = event.currentTarget.form?.querySelector<HTMLButtonElement>('button[type="submit"]');
      if (!submit?.disabled) event.currentTarget.form?.requestSubmit();
    }
    // Backspace in an empty field takes back the last dropped item.
    if (event.key === "Backspace" && event.currentTarget.value === "" && attachments.length > 0) {
      event.preventDefault();
      remove(attachments.at(-1)!.id);
    }
  };

  const handlePaste: ClipboardEventHandler<HTMLTextAreaElement> = (event) => {
    const files = [...(event.clipboardData?.files ?? [])];
    if (files.length === 0) return;
    event.preventDefault();
    add(files.map((file) => ({ name: file.name, kind: "file", file })));
  };

  return (
    <Textarea
      className={cn(className)}
      name="message"
      onCompositionEnd={() => setComposing(false)}
      onCompositionStart={() => setComposing(true)}
      onKeyDown={handleKeyDown}
      onPaste={handlePaste}
      placeholder={dragging && dropPlaceholder ? dropPlaceholder : placeholder}
      variant="bare"
      {...props}
    />
  );
};

export type PromptInputSubmitProps = ComponentProps<typeof Button> & { label: string };

export const PromptInputSubmit = ({ label, children, ...props }: PromptInputSubmitProps) => (
  <Button aria-label={label} size="icon" type="submit" {...props}>
    {children}
  </Button>
);

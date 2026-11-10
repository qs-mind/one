import {
  CheckIcon,
  ChevronDownIcon,
  FolderIcon,
  HouseIcon,
  PlusIcon,
  ReplyIcon,
  SearchIcon,
  SettingsIcon,
  Undo2Icon,
  UsersIcon,
  XIcon,
  type LucideIcon,
} from "lucide-react";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

const STILL: readonly [string, LucideIcon][] = [
  ["House", HouseIcon],
  ["Folder", FolderIcon],
  ["Users", UsersIcon],
  ["Settings", SettingsIcon],
  ["Search", SearchIcon],
  ["Check", CheckIcon],
  ["X", XIcon],
  ["Plus", PlusIcon],
  ["ChevronDown", ChevronDownIcon],
];
const TURNING: readonly [string, LucideIcon][] = [
  ["Undo2", Undo2Icon],
  ["Reply", ReplyIcon],
];

function Row({ icons, mirrored }: { icons: readonly [string, LucideIcon][]; mirrored?: boolean }) {
  return (
    <ul className="flex flex-wrap gap-4">
      {icons.map(([name, Icon]) => (
        <li key={name} className="flex w-24 flex-col items-center gap-1">
          <Icon aria-hidden className={mirrored ? "size-4.5 rtl:-scale-x-100" : "size-4.5"} />
          <span className="text-xs text-muted-foreground">
            <Code>{name}</Code>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function Icons() {
  const t = useText();
  return (
    <Demo id="icons" title="Icons">
      <State name={t(foundation.neverMirrors)}>
        <Row icons={STILL} />
      </State>
      <State name={t(foundation.mirrors)}>
        <Row icons={TURNING} mirrored />
      </State>
      <State name={<Code>18 · 22 / 1.6 · 16</Code>}>
        <span className="flex items-center gap-4">
          <HouseIcon aria-hidden className="size-4.5" />
          <HouseIcon aria-hidden className="size-5.5" strokeWidth={1.6} />
          <HouseIcon aria-hidden className="size-4" />
        </span>
      </State>
    </Demo>
  );
}

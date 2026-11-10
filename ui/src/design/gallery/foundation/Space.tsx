import { Num } from "@/design/Num";
import { Demo } from "../parts";

const STEPS = [2, 4, 6, 8, 12, 16, 20, 24, 28, 32, 40, 48, 56, 72];

export function Space() {
  return (
    <Demo id="space" title="Space">
      <ul className="flex w-full flex-col gap-2">
        {STEPS.map((px) => (
          <li key={px} className="flex items-center gap-4">
            <span className="w-12 shrink-0 text-xs text-muted-foreground">
              <Num value={px} />
            </span>
            <span aria-hidden className="h-2.5 rounded-full bg-foreground" style={{ width: `${px / 16}rem` }} />
          </li>
        ))}
      </ul>
    </Demo>
  );
}

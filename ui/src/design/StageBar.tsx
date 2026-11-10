// The stages of a plan or a tender as weighted segments: done, now (or waiting), pending.
// Its meaning is in `label`, in words; the first stage sits on the start side by itself.
import { cn } from "@/design/lib/utils";
import { stateFill, type StageState } from "@/design/now-waiting";

type StageBarProps = {
  stages: readonly { state: StageState; weight?: number }[];
  label: string;
  className?: string;
};

export function StageBar({ stages, label, className }: StageBarProps) {
  return (
    <div role="img" aria-label={label} className={cn("flex w-full gap-1", className)}>
      {stages.map((stage, index) => (
        <span
          // Stages have no id of their own; their order is their identity.
          key={index}
          data-state-fill={stage.state}
          className={cn("h-1.5 min-w-1 rounded-full transition-colors duration-240 ease-linear", stateFill[stage.state])}
          style={{ flex: `${stage.weight ?? 1} 1 0%` }}
        />
      ))}
    </div>
  );
}

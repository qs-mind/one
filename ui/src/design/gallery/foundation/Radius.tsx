import { Code, Demo, State } from "../parts";

const STEPS = [
  { name: "rounded-sm · 4", className: "rounded-sm" },
  { name: "rounded-lg · 10", className: "rounded-lg" },
  { name: "rounded-xl · 12", className: "rounded-xl" },
  { name: "rounded-2xl · 16", className: "rounded-2xl" },
  { name: "rounded-full", className: "rounded-full" },
] as const;

export function Radius() {
  return (
    <Demo id="radius" title="Radius">
      {STEPS.map((step) => (
        <State key={step.name} name={<Code>{step.name}</Code>}>
          <span aria-hidden className={`block h-14 w-24 border border-line bg-muted ${step.className}`} />
        </State>
      ))}
    </Demo>
  );
}

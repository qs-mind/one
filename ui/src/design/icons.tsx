// Icons that point along the reading direction, named by meaning so no screen picks "left" or "right" (3.6).
import { ArrowRightIcon, type LucideProps } from "lucide-react";
import { cn } from "@/design/lib/utils";

/** From one to the next: "Lead QS → Pricing QS" in English, mirrored in Arabic. */
export function IconForward({ className, ...props }: LucideProps) {
  return <ArrowRightIcon aria-hidden className={cn("rtl:-scale-x-100", className)} {...props} />;
}

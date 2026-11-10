// Every number, amount with its unit, percentage, item code and date range on screen: left to right, isolated,
// so "-5", "5%" or "7/03" never reorders inside Arabic. Never a sentence (Arabic words inside would read backwards).
import type { ReactNode } from "react";
import { cn } from "@/design/lib/utils";
import { formatNumber } from "@/texts/format";
import { useLang } from "@/texts/language";

type NumProps = {
  value?: number;
  options?: Intl.NumberFormatOptions;
  /** A ready string with no Arabic words: an item code "7/03", a unit "م³" or "ج.م". */
  children?: ReactNode;
  className?: string;
};

export function Num({ value, options, children, className }: NumProps) {
  const { lang } = useLang();
  return (
    <bdi dir="ltr" className={cn("num", className)}>
      {value === undefined ? children : formatNumber(value, lang, options)}
    </bdi>
  );
}

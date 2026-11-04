// Numbers on screen come from the core's decimal strings and never pass through parseFloat, so what is
// shown is exactly what the ledger holds. Western digits.

/** "39850.5" -> "39,850.50" with places 2. Places is a minimum: a digit the ledger holds is never cut. */
export function formatDecimal(value: string, places?: number): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return value; // not a plain decimal: show it as the core sent it
  const [, sign, whole = "", fraction = ""] = match;
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const decimals = places !== undefined && fraction.length < places ? fraction.padEnd(places, "0") : fraction;
  return `${sign}${grouped}${decimals ? `.${decimals}` : ""}`;
}

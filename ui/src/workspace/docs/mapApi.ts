import { api } from "../../api";
import type { Text } from "../../i18n";
import type { Anchor } from "../../project/types";
import type { PdfBox } from "../../deliverables/types";
export type Locator = {
  page?: number;
  sheet?: string;
  row?: number;
  col?: number;
  box?: PdfBox;
};
export type MapFile = {
  file_id: string;
  name: string;
  pages: number | null;
  read_how: string;
  ai_title: Text | null;
  key_pages: (Locator & { label: Text })[];
};
export type Group = { path: string; label: Text; count: number };
export type MapPage = {
  status: { waiting: number; reading: number; total: number; line: Text };
  groups: Group[];
  files: MapFile[];
  next_cursor: string | null;
};
export type FactSource = {
  value: string | null;
  file_id: string;
  locator: Locator;
  box?: PdfBox | null;
};
export type Fact = FactSource & {
  id: string;
  name: Text;
  unit?: string;
  currency?: string;
  state: "found" | "blank" | "conflict";
  conflict_with: (FactSource | string)[];
  confirmed_by: string | null;
  confirmed_at?: string | null;
  corrected_value: string | null;
};
export type MapLink = {
  id: string;
  from_file_id: string;
  from_locator: Locator;
  to_file_id: string;
  to_locator: Locator;
  words: Text;
};
export const anchorOf = (l: Locator, box?: PdfBox | null): Anchor => ({
  ...(l.page ? { page: l.page } : {}),
  ...(l.sheet ? { sheet: l.sheet } : {}),
  ...(l.row ? { row: `r${l.row}` } : {}),
  ...(box ?? l.box ? { box: (box ?? l.box)! } : {}),
});
export function mapApi(projectId: string) {
  const base = `/projects/${encodeURIComponent(projectId)}/map`;
  async function read<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await api(base + path, init);
    if (!r.ok) throw new Error("map");
    return r.json();
  }
  return {
    page: (parent?: string, cursor?: string) =>
      read<MapPage>(
        `?${new URLSearchParams({
          limit: "100",
          ...(parent ? { parent } : {}),
          ...(cursor ? { cursor } : {}),
        })}`,
      ),
    facts: (cursor?: string) =>
      read<{ facts: Fact[]; next_cursor: string | null }>(
        `/facts?${new URLSearchParams({
          limit: "100",
          ...(cursor ? { cursor } : {}),
        })}`,
      ),
    links: (cursor?: string) =>
      read<{ links: MapLink[]; next_cursor: string | null }>(
        `/links?${new URLSearchParams({
          limit: "100",
          ...(cursor ? { cursor } : {}),
        })}`,
      ),
    update: (id: string, body: { confirm: true } | { value: string }) =>
      read<unknown>(`/facts/${encodeURIComponent(id)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
  };
}

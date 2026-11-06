import { api } from "../../api";
import { coreLine } from "../../core";
import { texts, type Text } from "../../i18n";
import { SourceError } from "../../project/sources";

export type Citation = { file_id: string; name: string; date: string; page: number };
export type ChangedPage = {
  old: Citation; new: Citation; method: "sheet" | "title" | "order";
  added: string[]; removed: string[]; pixels_changed: number; overlay: boolean; summary: Text;
};
export type Comparison = {
  old: Omit<Citation, "page">; new: Omit<Citation, "page">; compared_at: string;
  pairs: unknown[]; changed: ChangedPage[]; unchanged: number;
  unpaired_old: Citation[]; unpaired_new: Citation[];
};
export type CompareFile = { id: string; name: string; added_at: string; replaces?: string | null; kind?: string };
const base = (project: string) => `/projects/${encodeURIComponent(project)}/files`;
async function checked(path: string, init?: RequestInit) {
  const response = await api(path, init).catch(() => undefined);
  if (!response?.ok) throw new SourceError(await coreLine(response, texts.compareFailed));
  return response;
}
export const compareApi = {
  async files(project: string): Promise<CompareFile[]> {
    const result = await (await checked(`${base(project)}?include_old=true`)).json();
    return result.files.filter((f: CompareFile) => f.kind === "pdf");
  },
  async compare(project: string, old: string, newer: string): Promise<Comparison> {
    return (await checked(`${base(project)}/compare`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_file_id: old, new_file_id: newer }) })).json();
  },
  async overlay(project: string, old: string, newer: string, before: number, after: number, width: number): Promise<string> {
    const query = new URLSearchParams({ old_file_id: old, new_file_id: newer, old_page: String(before), new_page: String(after), width: String(width) });
    const response = await checked(`${base(project)}/compare/overlay?${query}`);
    return URL.createObjectURL(await response.blob());
  },
};

// The routes of today that Settings keeps using (contract section 5): the AI providers and the models per role, the
// web search key, Claude Code, what is spent, the Connectors, the Backup and Undo. Their shapes are written here as
// the core answers them; every call leaves through api() and never throws (existing.ts).
import { call } from "./existing";
import type { Schemas } from "./client";

type Text = Schemas["Text"];

// The AI providers and the models (GET /settings/ai, PUT /settings/ai/roles) -----------------------------------------

export type Role = "lead" | "checker" | "specialist" | "quick";
export const ROLES: readonly Role[] = ["lead", "checker", "specialist", "quick"];
export type ModelChoice = { connector: string; model: string };
export type ModelCard = ModelChoice & { name: string; provider: string; on_device: boolean };
export type AiConnector = {
  id: string; // "anthropic", "standard:<id>" or "claude-code"
  kind: "model" | "agent";
  name: string;
  provider: string;
  on_device: boolean;
  key_set: boolean;
  error: Text | null; // why its models could not be listed just now
};
export type AiSettings = {
  connectors: AiConnector[];
  sheet: ModelCard[];
  roles: Partial<Record<Role, ModelChoice>>;
  defaults: Partial<Record<Role, ModelChoice>>;
};

export const getAiSettings = () => call<AiSettings>("/settings/ai");
export const chooseModel = (role: Role, choice: ModelChoice) =>
  call<Partial<Record<Role, ModelChoice>>>("/settings/ai/roles", "PUT", { [role]: choice });

/** Claude Code is not a link (contract 23-24): it is switched off here and on by its check (existing.ts). */
export const switchOffClaudeCode = () => call<{ on: boolean }>("/settings/ai/claude-code", "PUT", { path: null, on: false });

// The web search key (contract Q21: Settings, AI) -------------------------------------------------------------------

export type SearchState = { provider: string | null; own_key: boolean };
export const getSearch = () => call<SearchState>("/settings/search");
export const saveSearchKey = (value: string) => call<{ set: boolean }>("/settings/search-key", "PUT", { value });

// What is spent (GET /costs): exact decimal text in USD ---------------------------------------------------------------

export type Spent = { today: string; month: string; equivalent: { today: string | null; month: string | null } };
export const getSpent = () => call<Spent>("/costs");

// Connectors -----------------------------------------------------------------------------------------------------------

export type ConnectorRow = { name: string; transport: "stdio" | "http"; runs: string; enabled: boolean; tools: number };
export const getConnectors = () => call<{ connectors: ConnectorRow[] }>("/connectors");
export const setConnectorOn = (name: string, enabled: boolean) =>
  call<{ connector: ConnectorRow }>(`/connectors/${encodeURIComponent(name)}/enabled`, "PUT", { enabled });
export const removeConnector = (name: string) => call<Schemas["Undoable"]>(`/connectors/${encodeURIComponent(name)}`, "DELETE");

// Backup ---------------------------------------------------------------------------------------------------------------

export type BackupState = {
  folder: string | null;
  reachable: boolean;
  last_run: string | null;
  note: Text | null;
  projects: { id: string; last_backup: string | null; confidential: boolean }[];
};
export const getBackup = () => call<BackupState>("/backup");
export const setBackupFolder = (path: string) => call<BackupState>("/backup/folder", "PUT", { path });
export const runBackup = () => call<{ backed_up: number }>("/backup/run", "POST");

// Undo -----------------------------------------------------------------------------------------------------------------

/** Takes back a removal within its window; true when the core put it back. */
export async function undo(token: string): Promise<boolean> {
  const answer = await call<unknown>(`/undo/${token}`, "POST");
  return answer.error === undefined;
}

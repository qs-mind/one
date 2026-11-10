// The routes of today that Settings keeps using (contract section 5): the AI providers, the models per role and their
// prices, the web search key, Claude Code, what is spent, the Connectors, the Backup, the QS Mind account and Undo. Their shapes are written here as
// the core answers them; every call leaves through api() and never throws (existing.ts).
import { call } from "./existing";
import type { Schemas } from "./client";

type Text = Schemas["Text"];

// The AI providers and the models (GET /settings/ai, PUT /settings/ai/roles) -----------------------------------------

export type Role = "lead" | "checker" | "specialist" | "quick";
export const ROLES: readonly Role[] = ["lead", "checker", "specialist", "quick"];
export type ModelChoice = { connector: string; model: string };
export type ModelCard = ModelChoice & {
  name: string;
  provider: string;
  on_device: boolean;
  price_in: string | null; // USD per million tokens, exact decimal text; null when ONE does not know it
  price_out: string | null;
};
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

/** A price ONE does not know, entered by the engineer (USD per million tokens, exact decimal text). A number that is
 * not exact answers 422 with the core's words. */
export const enterPrice = (choice: ModelChoice, price: { in: string; out: string }) =>
  call<ModelCard>("/settings/ai/prices", "PUT", { ...choice, ...price });

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

/** What the core found a Connector being added can do: its card, answered with "yes" (and its questions) or "no". */
export type ConnectorTool = { name: string; purpose: string | null; read_only: boolean; destructive: boolean; open_world: boolean };
export type ConnectorAsk = {
  id: string;
  title: Text;
  detail: Text;
  options: string[];
  payload: { tools: ConnectorTool[]; questions: { id: string; options?: string[] }[] };
};
export type ConnectorIn = { name: string; transport: "stdio" | "http"; command?: string; url?: string; token?: string };
/** Starts the Connector to see what it can do; nothing is saved until its card is answered. */
export const addConnector = (body: ConnectorIn) => call<{ card: ConnectorAsk }>("/connectors", "POST", body);
export const answerConnector = (id: string, choice: string, answers?: Record<string, string>) =>
  call<{ connector: ConnectorRow | null }>(`/connectors/cards/${encodeURIComponent(id)}`, "POST", answers ? { choice, answers } : { choice });

// Backup ---------------------------------------------------------------------------------------------------------------

export type BackupState = {
  folder: string | null;
  reachable: boolean;
  last_run: string | null;
  note: Text | null;
  backup_key: { local: boolean; in_account: boolean; code_saved: boolean };
  projects: { id: string; last_backup: string | null; confidential: boolean }[];
};
export const getBackup = () => call<BackupState>("/backup");
export const setBackupFolder = (path: string) => call<BackupState>("/backup/folder", "PUT", { path });
export const runBackup = () => call<{ backed_up: number }>("/backup/run", "POST");

/** A tender found in a backup folder, and what restoring it needs: nothing, a sign-in, or a recovery code. */
export type FoundTender = { id: string; name: string | null; last_backup: string; needs: null | "sign_in" | "backup_code" | "project_code" };
export const findBackups = (path: string) => call<{ projects: FoundTender[] }>(`/backup/found?path=${encodeURIComponent(path)}`);
export const restoreTender = (path: string, id: string, code?: string) =>
  call<{ id: string; name: string }>("/backup/restore", "POST", code ? { path, project_id: id, code } : { path, project_id: id });
/** The Backup key's recovery code: in this one answer only, never stored. */
export const makeRecoveryCode = () => call<{ code: string }>("/backup/recovery-code", "POST");
export const confirmRecoveryCode = (last_group: string) => call<{ saved: true }>("/backup/recovery-code/confirm", "POST", { last_group });

// The QS Mind account: signing in is in existing.ts (first launch uses it too) -----------------------------------------

export const signOut = () => call<{ state: "signed_out" }>("/account", "DELETE");

// Undo -----------------------------------------------------------------------------------------------------------------

/** Takes back a removal within its window; true when the core put it back. */
export async function undo(token: string): Promise<boolean> {
  const answer = await call<unknown>(`/undo/${token}`, "POST");
  return answer.error === undefined;
}

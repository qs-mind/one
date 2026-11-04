"""The project file's schema as migrations, counted by `PRAGMA user_version`.

`MIGRATIONS[n]` takes a file from version n to n + 1. Only ever append; never edit a shipped entry.
"""

SCHEMA_1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE files (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, size INTEGER NOT NULL,
  sha256 TEXT NOT NULL, status TEXT NOT NULL, note TEXT, pages INTEGER,
  added_at TEXT NOT NULL, added_by TEXT NOT NULL,
  replaces TEXT REFERENCES files(id), valid_until TEXT);
CREATE INDEX files_sha ON files(sha256);
CREATE INDEX files_current_name ON files(name) WHERE valid_until IS NULL;
CREATE TABLE file_pieces (id INTEGER PRIMARY KEY, sha256 TEXT NOT NULL, seq INTEGER NOT NULL,
  data BLOB NOT NULL, UNIQUE (sha256, seq));
CREATE TABLE chunks (id INTEGER PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id),
  seq INTEGER NOT NULL, locator TEXT NOT NULL CHECK (json_valid(locator)), text TEXT NOT NULL);
CREATE INDEX chunks_file ON chunks(file_id, seq);
CREATE VIRTUAL TABLE chunks_fts USING fts5(norm, content='', contentless_delete=1,
  tokenize='unicode61 remove_diacritics 0');
CREATE TABLE sources (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL,
  file_id TEXT REFERENCES files(id),
  locator TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(locator)),
  url TEXT, dated TEXT, recorded_at TEXT NOT NULL, recorded_by TEXT NOT NULL);
CREATE TABLE items (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL, code TEXT,
  fields TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(fields) AND json_type(fields) = 'object'),
  version INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL, created_by TEXT NOT NULL,
  updated_at TEXT NOT NULL, updated_by TEXT NOT NULL);
CREATE INDEX items_code ON items(code);
CREATE TABLE numbers (
  id TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES items(id), name TEXT NOT NULL,
  value TEXT NOT NULL, unit TEXT, currency TEXT,
  source_id TEXT NOT NULL REFERENCES sources(id), dated TEXT NOT NULL,
  recorded_at TEXT NOT NULL, recorded_by TEXT NOT NULL,
  replaces TEXT REFERENCES numbers(id), reason TEXT, valid_until TEXT,
  CHECK (replaces IS NULL OR length(trim(reason)) > 0));
CREATE INDEX numbers_item ON numbers(item_id, name);
CREATE TABLE audit (id INTEGER PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL,
  action TEXT NOT NULL, table_name TEXT NOT NULL, row_id TEXT NOT NULL, before TEXT, after TEXT);
CREATE INDEX audit_row ON audit(row_id);
-- The Guardrail inside the file. A number changes in one way only:
-- a current one is marked valid_until.
CREATE TRIGGER numbers_no_delete BEFORE DELETE ON numbers
  BEGIN SELECT RAISE(ABORT, 'Source Ledger numbers are never deleted'); END;
CREATE TRIGGER numbers_only_valid_until BEFORE UPDATE ON numbers
  WHEN OLD.valid_until IS NOT NULL OR NEW.valid_until IS NULL
    OR NEW.id IS NOT OLD.id OR NEW.item_id IS NOT OLD.item_id OR NEW.name IS NOT OLD.name
    OR NEW.value IS NOT OLD.value OR NEW.unit IS NOT OLD.unit OR NEW.currency IS NOT OLD.currency
    OR NEW.source_id IS NOT OLD.source_id OR NEW.dated IS NOT OLD.dated
    OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.recorded_by IS NOT OLD.recorded_by
    OR NEW.replaces IS NOT OLD.replaces OR NEW.reason IS NOT OLD.reason
  BEGIN SELECT RAISE(ABORT, 'Source Ledger numbers are corrected by a new entry'); END;
-- sources: no UPDATE, no DELETE. audit: no UPDATE, no DELETE. files, items: no DELETE.
CREATE TRIGGER sources_no_update BEFORE UPDATE ON sources
  BEGIN SELECT RAISE(ABORT, 'Sources are never edited'); END;
CREATE TRIGGER sources_no_delete BEFORE DELETE ON sources
  BEGIN SELECT RAISE(ABORT, 'Sources are never deleted'); END;
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit
  BEGIN SELECT RAISE(ABORT, 'The audit trail is never edited'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit
  BEGIN SELECT RAISE(ABORT, 'The audit trail is never deleted'); END;
CREATE TRIGGER files_no_delete BEFORE DELETE ON files
  BEGIN SELECT RAISE(ABORT, 'Files are never deleted; a new version replaces them'); END;
CREATE TRIGGER items_no_delete BEFORE DELETE ON items
  BEGIN SELECT RAISE(ABORT, 'Items are never deleted'); END;
"""

MIGRATIONS: list[str] = [SCHEMA_1]

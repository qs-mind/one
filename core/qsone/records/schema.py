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

# The QS Calc Engine. A calculation, like a number, changes in one way only: it is marked
# valid_until when a newer version replaces it. Its inputs are never edited or deleted.
SCHEMA_2 = """
CREATE TABLE calculations (
  id TEXT PRIMARY KEY,
  formula TEXT NOT NULL,
  request TEXT NOT NULL CHECK (json_valid(request)),
  value TEXT NOT NULL, unit TEXT NOT NULL,
  exact INTEGER NOT NULL CHECK (exact IN (0, 1)),
  trace TEXT NOT NULL CHECK (json_valid(trace)),
  engine INTEGER NOT NULL,
  output TEXT NOT NULL REFERENCES numbers(id),
  recorded_at TEXT NOT NULL, recorded_by TEXT NOT NULL,
  replaces TEXT REFERENCES calculations(id), reason TEXT, valid_until TEXT,
  CHECK (replaces IS NULL OR length(trim(reason)) > 0));
CREATE INDEX calculations_output ON calculations(output);
CREATE TABLE calc_inputs (
  calc_id TEXT NOT NULL REFERENCES calculations(id),
  name TEXT NOT NULL,
  seq INTEGER NOT NULL,
  number_id TEXT NOT NULL REFERENCES numbers(id),
  PRIMARY KEY (calc_id, name, seq));
CREATE INDEX calc_inputs_number ON calc_inputs(number_id);
CREATE TRIGGER calculations_no_delete BEFORE DELETE ON calculations
  BEGIN SELECT RAISE(ABORT, 'Calculations are never deleted'); END;
CREATE TRIGGER calculations_only_valid_until BEFORE UPDATE ON calculations
  WHEN OLD.valid_until IS NOT NULL OR NEW.valid_until IS NULL
    OR NEW.id IS NOT OLD.id OR NEW.formula IS NOT OLD.formula OR NEW.request IS NOT OLD.request
    OR NEW.value IS NOT OLD.value OR NEW.unit IS NOT OLD.unit OR NEW.exact IS NOT OLD.exact
    OR NEW.trace IS NOT OLD.trace OR NEW.engine IS NOT OLD.engine OR NEW.output IS NOT OLD.output
    OR NEW.recorded_at IS NOT OLD.recorded_at OR NEW.recorded_by IS NOT OLD.recorded_by
    OR NEW.replaces IS NOT OLD.replaces OR NEW.reason IS NOT OLD.reason
  BEGIN SELECT RAISE(ABORT, 'Calculations are replaced by a new version'); END;
CREATE TRIGGER calc_inputs_no_update BEFORE UPDATE ON calc_inputs
  BEGIN SELECT RAISE(ABORT, 'Calculation inputs are never edited'); END;
CREATE TRIGGER calc_inputs_no_delete BEFORE DELETE ON calc_inputs
  BEGIN SELECT RAISE(ABORT, 'Calculation inputs are never deleted'); END;
"""

# The agent engine (Plan 4): Checkpoints, approvals, writes made, the team's messages,
# Deliverable drafts, Reviews and AI costs. In every Records file, project and Engineer Records.
SCHEMA_3 = """
CREATE TABLE briefs (id TEXT PRIMARY KEY, chat_id TEXT NOT NULL, text TEXT NOT NULL,
  status TEXT NOT NULL, step TEXT CHECK (step IS NULL OR json_valid(step)),
  read_untrusted INTEGER NOT NULL DEFAULT 0,
  allowed TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(allowed)),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX briefs_chat ON briefs(chat_id, created_at);
CREATE TABLE agent_runs (id TEXT PRIMARY KEY, brief_id TEXT NOT NULL REFERENCES briefs(id),
  parent_id TEXT REFERENCES agent_runs(id), spec TEXT NOT NULL CHECK (json_valid(spec)),
  connector TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL, history BLOB,
  session_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX agent_runs_brief ON agent_runs(brief_id, created_at);
CREATE TABLE deferred_results (run_id TEXT NOT NULL REFERENCES agent_runs(id),
  call_id TEXT NOT NULL, result TEXT NOT NULL, PRIMARY KEY (run_id, call_id));
CREATE TABLE approvals (id TEXT PRIMARY KEY, brief_id TEXT NOT NULL REFERENCES briefs(id),
  run_id TEXT, call_id TEXT, card TEXT NOT NULL CHECK (json_valid(card)),
  status TEXT NOT NULL CHECK (status IN ('pending', 'settled', 'withdrawn')), choice TEXT,
  asked_at TEXT NOT NULL, settled_at TEXT);
CREATE INDEX approvals_brief ON approvals(brief_id, status);
CREATE TABLE brief_writes (brief_id TEXT NOT NULL, key TEXT NOT NULL, result_id TEXT NOT NULL,
  PRIMARY KEY (brief_id, key));
CREATE TABLE team_messages (id TEXT PRIMARY KEY, brief_id TEXT NOT NULL, at TEXT NOT NULL,
  sender TEXT NOT NULL, recipient TEXT NOT NULL, text TEXT NOT NULL);
CREATE INDEX team_messages_brief ON team_messages(brief_id, at);
CREATE TABLE deliverables (id TEXT PRIMARY KEY, brief_id TEXT NOT NULL, run_id TEXT NOT NULL,
  draft TEXT NOT NULL CHECK (json_valid(draft)), replaces TEXT REFERENCES deliverables(id),
  created_at TEXT NOT NULL);
CREATE INDEX deliverables_brief ON deliverables(brief_id, created_at);
CREATE TABLE reviews (id TEXT PRIMARY KEY,
  deliverable_id TEXT NOT NULL REFERENCES deliverables(id), round INTEGER NOT NULL,
  code TEXT NOT NULL CHECK (code IN ('A', 'B', 'C')), comments TEXT NOT NULL,
  checker TEXT NOT NULL, same_provider INTEGER NOT NULL, at TEXT NOT NULL);
CREATE INDEX reviews_deliverable ON reviews(deliverable_id);
CREATE TABLE ai_costs (id INTEGER PRIMARY KEY, at TEXT NOT NULL, local_day TEXT NOT NULL,
  brief_id TEXT NOT NULL, project_id TEXT, run_id TEXT NOT NULL, role TEXT NOT NULL,
  connector TEXT NOT NULL, model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL, usd TEXT, equivalent INTEGER NOT NULL DEFAULT 0,
  basis TEXT NOT NULL);
CREATE INDEX ai_costs_day ON ai_costs(local_day);
CREATE INDEX ai_costs_brief ON ai_costs(brief_id);
-- ai_costs, reviews, team_messages: no UPDATE, no DELETE.
-- deferred_results, brief_writes: no UPDATE.
CREATE TRIGGER ai_costs_no_update BEFORE UPDATE ON ai_costs
  BEGIN SELECT RAISE(ABORT, 'AI costs are never edited'); END;
CREATE TRIGGER ai_costs_no_delete BEFORE DELETE ON ai_costs
  BEGIN SELECT RAISE(ABORT, 'AI costs are never deleted'); END;
CREATE TRIGGER reviews_no_update BEFORE UPDATE ON reviews
  BEGIN SELECT RAISE(ABORT, 'Reviews are never edited'); END;
CREATE TRIGGER reviews_no_delete BEFORE DELETE ON reviews
  BEGIN SELECT RAISE(ABORT, 'Reviews are never deleted'); END;
CREATE TRIGGER team_messages_no_update BEFORE UPDATE ON team_messages
  BEGIN SELECT RAISE(ABORT, 'Team messages are never edited'); END;
CREATE TRIGGER team_messages_no_delete BEFORE DELETE ON team_messages
  BEGIN SELECT RAISE(ABORT, 'Team messages are never deleted'); END;
CREATE TRIGGER deferred_results_no_update BEFORE UPDATE ON deferred_results
  BEGIN SELECT RAISE(ABORT, 'A stored tool result is never edited'); END;
CREATE TRIGGER brief_writes_no_update BEFORE UPDATE ON brief_writes
  BEGIN SELECT RAISE(ABORT, 'A remembered write is never edited'); END;
"""

# Deliverables and review (Plan 6). Plan 4's Deliverable drafts (an agent's answer as the
# Checking QS sees it) keep their rows and Reviews under a name that says what they are, so
# `deliverables` names the Deliverable itself: a Sheet or a Document, its parts (rows and
# blocks, never deleted), Suggested changes, Saved versions, Revisions, checks, comments, Fill
# Plans and Review reports. A Saved version is rebuilt from the parts, the audit trail and the
# ledger as of its time; a Revision keeps a frozen snapshot with its SHA-256.
SCHEMA_4 = """
ALTER TABLE deliverables RENAME TO deliverable_drafts;
DROP INDEX deliverables_brief;
CREATE INDEX deliverable_drafts_brief ON deliverable_drafts(brief_id, created_at);
CREATE TABLE deliverables (
  id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK (kind IN ('sheet','document')),
  variant TEXT NOT NULL, title TEXT NOT NULL,
  language TEXT NOT NULL CHECK (language IN ('ar','en')),
  template TEXT NOT NULL CHECK (json_valid(template)),
  total_item_id TEXT REFERENCES items(id),
  desk TEXT CHECK (desk IS NULL OR json_valid(desk)), off_desk INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, created_by TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE parts (
  rowid_ INTEGER PRIMARY KEY, id TEXT NOT NULL,
  deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  seq REAL NOT NULL, kind TEXT NOT NULL CHECK (kind IN ('section','item','block')),
  item_id TEXT REFERENCES items(id), node TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(node)),
  version INTEGER NOT NULL, valid_from TEXT NOT NULL, valid_until TEXT,
  removed INTEGER NOT NULL DEFAULT 0);
CREATE UNIQUE INDEX parts_current ON parts(id) WHERE valid_until IS NULL;
CREATE INDEX parts_deliverable ON parts(deliverable_id, valid_from);
CREATE TABLE changes (
  id TEXT PRIMARY KEY, deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  op TEXT NOT NULL CHECK (json_valid(op)), reason TEXT, author TEXT NOT NULL,
  comment_id TEXT, status TEXT NOT NULL CHECK (status IN ('pending','accepted','rejected','stale')),
  created_at TEXT NOT NULL, decided_at TEXT, decided_by TEXT, version_n INTEGER);
CREATE INDEX changes_pending ON changes(deliverable_id) WHERE status = 'pending';
CREATE TABLE versions (deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  n INTEGER NOT NULL, at TEXT NOT NULL, by TEXT NOT NULL,
  changes TEXT NOT NULL CHECK (json_valid(changes)),
  PRIMARY KEY (deliverable_id, n));
CREATE TABLE revisions (deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  no INTEGER NOT NULL, version_n INTEGER NOT NULL, issued_at TEXT NOT NULL, issued_by TEXT NOT NULL,
  signed_off INTEGER NOT NULL DEFAULT 0, snapshot BLOB NOT NULL, sha256 TEXT NOT NULL,
  PRIMARY KEY (deliverable_id, no));
CREATE TABLE checks (id TEXT PRIMARY KEY, deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  version_n INTEGER NOT NULL, code TEXT NOT NULL CHECK (code IN ('A','B','C')),
  checker TEXT NOT NULL, same_provider INTEGER NOT NULL, summary TEXT, at TEXT NOT NULL);
CREATE TABLE comments (
  id TEXT PRIMARY KEY, deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  parent_id TEXT REFERENCES comments(id), kind TEXT NOT NULL CHECK (kind IN ('note','review')),
  anchor TEXT NOT NULL CHECK (json_valid(anchor)), body TEXT NOT NULL, author TEXT NOT NULL,
  code TEXT CHECK (code IS NULL OR code IN ('B','C')), check_id TEXT REFERENCES checks(id),
  status TEXT NOT NULL CHECK (status IN ('open','closed')), version_n INTEGER NOT NULL,
  created_at TEXT NOT NULL, closed_at TEXT, closed_by TEXT, fix_asked_at TEXT);
CREATE INDEX comments_deliverable ON comments(deliverable_id, status);
CREATE TABLE fill_plans (id TEXT PRIMARY KEY,
  deliverable_id TEXT NOT NULL REFERENCES deliverables(id),
  file_id TEXT NOT NULL REFERENCES files(id), plan TEXT NOT NULL CHECK (json_valid(plan)),
  created_at TEXT NOT NULL, created_by TEXT NOT NULL);
CREATE TABLE review_reports (deliverable_id TEXT NOT NULL, revision_no INTEGER NOT NULL,
  body BLOB NOT NULL, at TEXT NOT NULL, PRIMARY KEY (deliverable_id, revision_no));
-- Guardrails inside the file: versions, revisions, checks, review_reports never change or go;
-- parts change only by valid_until; changes and comments are never deleted.
CREATE TRIGGER parts_no_delete BEFORE DELETE ON parts
  BEGIN SELECT RAISE(ABORT, 'Parts are never deleted'); END;
CREATE TRIGGER parts_only_valid_until BEFORE UPDATE ON parts
  WHEN OLD.valid_until IS NOT NULL OR NEW.valid_until IS NULL OR NEW.node IS NOT OLD.node
    OR NEW.seq IS NOT OLD.seq OR NEW.id IS NOT OLD.id OR NEW.version IS NOT OLD.version
    OR NEW.removed IS NOT OLD.removed OR NEW.item_id IS NOT OLD.item_id
    OR NEW.rowid_ IS NOT OLD.rowid_ OR NEW.deliverable_id IS NOT OLD.deliverable_id
    OR NEW.kind IS NOT OLD.kind OR NEW.valid_from IS NOT OLD.valid_from
  BEGIN SELECT RAISE(ABORT, 'A part changes by a new row version'); END;
CREATE TRIGGER versions_no_update BEFORE UPDATE ON versions
  BEGIN SELECT RAISE(ABORT, 'Saved versions are never edited'); END;
CREATE TRIGGER versions_no_delete BEFORE DELETE ON versions
  BEGIN SELECT RAISE(ABORT, 'Saved versions are never deleted'); END;
CREATE TRIGGER revisions_no_update BEFORE UPDATE ON revisions
  BEGIN SELECT RAISE(ABORT, 'Revisions are never edited'); END;
CREATE TRIGGER revisions_no_delete BEFORE DELETE ON revisions
  BEGIN SELECT RAISE(ABORT, 'Revisions are never deleted'); END;
CREATE TRIGGER checks_no_update BEFORE UPDATE ON checks
  BEGIN SELECT RAISE(ABORT, 'Checks are never edited'); END;
CREATE TRIGGER checks_no_delete BEFORE DELETE ON checks
  BEGIN SELECT RAISE(ABORT, 'Checks are never deleted'); END;
CREATE TRIGGER review_reports_no_update BEFORE UPDATE ON review_reports
  BEGIN SELECT RAISE(ABORT, 'Review reports are never edited'); END;
CREATE TRIGGER review_reports_no_delete BEFORE DELETE ON review_reports
  BEGIN SELECT RAISE(ABORT, 'Review reports are never deleted'); END;
CREATE TRIGGER changes_no_delete BEFORE DELETE ON changes
  BEGIN SELECT RAISE(ABORT, 'Suggested changes are never deleted'); END;
CREATE TRIGGER comments_no_delete BEFORE DELETE ON comments
  BEGIN SELECT RAISE(ABORT, 'Comments are never deleted'); END;
CREATE TRIGGER deliverables_no_delete BEFORE DELETE ON deliverables
  BEGIN SELECT RAISE(ABORT, 'Deliverables are never deleted'); END;
CREATE TRIGGER fill_plans_no_delete BEFORE DELETE ON fill_plans
  BEGIN SELECT RAISE(ABORT, 'Fill Plans are never deleted'); END;
"""

# Tools (Plan 5): the Web Log, hidden-text flags, Sandbox runs, Connector calls, and in
# Engineer Records the what-to-keep answers and the QS Mind price cache. Every Records file
# has these tables; the cache and the keep policy are used only in Engineer Records.
TOOLS_SQL = """
CREATE TABLE web_log (
  id TEXT PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, brief_id TEXT,
  action TEXT NOT NULL CHECK (action IN ('search', 'read')),
  provider TEXT, query TEXT, url TEXT, final_url TEXT, status INTEGER, title TEXT,
  dated TEXT, dated_how TEXT CHECK (dated_how IS NULL OR dated_how IN ('page', 'server')),
  file_id TEXT REFERENCES files(id),
  results TEXT CHECK (results IS NULL OR json_valid(results)));
CREATE TABLE file_flags (
  id INTEGER PRIMARY KEY, file_id TEXT NOT NULL REFERENCES files(id), kind TEXT NOT NULL,
  locator TEXT NOT NULL CHECK (json_valid(locator)), excerpt TEXT NOT NULL, count INTEGER NOT NULL);
CREATE INDEX file_flags_file ON file_flags(file_id);
CREATE TABLE sandbox_runs (
  id TEXT PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, brief_id TEXT, script TEXT NOT NULL,
  script_sha256 TEXT NOT NULL, inputs TEXT NOT NULL CHECK (json_valid(inputs)),
  params TEXT NOT NULL CHECK (json_valid(params)), limits TEXT NOT NULL CHECK (json_valid(limits)),
  exit INTEGER, ended TEXT NOT NULL, seconds TEXT NOT NULL,
  outputs TEXT NOT NULL CHECK (json_valid(outputs)), printed TEXT NOT NULL);
CREATE TABLE connector_calls (
  id TEXT PRIMARY KEY, at TEXT NOT NULL, actor TEXT NOT NULL, brief_id TEXT,
  connector TEXT NOT NULL, tool TEXT NOT NULL, args TEXT NOT NULL CHECK (json_valid(args)),
  ok INTEGER NOT NULL,
  result_sha256 TEXT, file_ids TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(file_ids)));
CREATE TABLE keep_policy (kind TEXT PRIMARY KEY,
  decision TEXT NOT NULL CHECK (decision IN ('keep', 'never')),
  decided_at TEXT NOT NULL, card_id TEXT NOT NULL);
CREATE TABLE price_cache (country TEXT NOT NULL, item_id TEXT NOT NULL, day TEXT,
  payload TEXT NOT NULL CHECK (json_valid(payload)), PRIMARY KEY (country, item_id));
CREATE TABLE price_cache_meta (country TEXT PRIMARY KEY, fetched_at TEXT NOT NULL, last_day TEXT);
-- rowid = price_cache.rowid
CREATE VIRTUAL TABLE price_cache_fts USING fts5(norm, content='', contentless_delete=1,
  tokenize='unicode61 remove_diacritics 0');
-- web_log, file_flags, sandbox_runs, connector_calls: no UPDATE, no DELETE.
-- keep_policy: no DELETE; a decision changes only through the tool, audited.
CREATE TRIGGER web_log_no_update BEFORE UPDATE ON web_log
  BEGIN SELECT RAISE(ABORT, 'The Web Log is never edited'); END;
CREATE TRIGGER web_log_no_delete BEFORE DELETE ON web_log
  BEGIN SELECT RAISE(ABORT, 'The Web Log is never deleted'); END;
CREATE TRIGGER file_flags_no_update BEFORE UPDATE ON file_flags
  BEGIN SELECT RAISE(ABORT, 'Hidden-text flags are never edited'); END;
CREATE TRIGGER file_flags_no_delete BEFORE DELETE ON file_flags
  BEGIN SELECT RAISE(ABORT, 'Hidden-text flags are never deleted'); END;
CREATE TRIGGER sandbox_runs_no_update BEFORE UPDATE ON sandbox_runs
  BEGIN SELECT RAISE(ABORT, 'Sandbox runs are never edited'); END;
CREATE TRIGGER sandbox_runs_no_delete BEFORE DELETE ON sandbox_runs
  BEGIN SELECT RAISE(ABORT, 'Sandbox runs are never deleted'); END;
CREATE TRIGGER connector_calls_no_update BEFORE UPDATE ON connector_calls
  BEGIN SELECT RAISE(ABORT, 'Connector calls are never edited'); END;
CREATE TRIGGER connector_calls_no_delete BEFORE DELETE ON connector_calls
  BEGIN SELECT RAISE(ABORT, 'Connector calls are never deleted'); END;
CREATE TRIGGER keep_policy_no_delete BEFORE DELETE ON keep_policy
  BEGIN SELECT RAISE(ABORT, 'What-to-keep answers are never deleted'); END;
"""

# The Project Canvas (Plan 7): where each frame sits and the last view, keyed `kind:ref`. Screen
# layout, not project facts: not audited, and floats are allowed. A Brief keeps what the engineer
# had selected on the canvas when sending it (JSON list of SelectionItem, or NULL).
CANVAS_SQL = """
CREATE TABLE canvas_frames (
  key TEXT PRIMARY KEY CHECK (key GLOB '[a-z]*:*'),
  x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,
  z INTEGER NOT NULL DEFAULT 0, collapsed INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL);
CREATE TABLE canvas_view (id INTEGER PRIMARY KEY CHECK (id = 1),
  x REAL NOT NULL, y REAL NOT NULL, zoom REAL NOT NULL, updated_at TEXT NOT NULL);
ALTER TABLE briefs ADD COLUMN selection TEXT CHECK (selection IS NULL OR json_valid(selection))
"""

# A tender folder (Plan 8): the path inside the dropped folder a file came from, display text
# only, as its name is. NULL for a file added on its own.
FOLDERS_SQL = "ALTER TABLE files ADD COLUMN folder TEXT"

# The Lead QS's effort, picked in the message box: kept with its Brief (NULL: the provider's own),
# and with each AI cost, so the Brief Budget measures each effort's tokens apart.
EFFORT_SQL = """
ALTER TABLE briefs ADD COLUMN effort TEXT CHECK (effort IN ('low', 'medium', 'high'));
ALTER TABLE ai_costs ADD COLUMN effort TEXT
"""

# A Brief's work log: each step its team reported with its real start and end, and the Brief's
# own (JSON, `engine.worklog`), so the chat shows "Worked for 2m · 6 steps" after a reload too.
WORKLOG_SQL = (
    "ALTER TABLE briefs ADD COLUMN worklog TEXT CHECK (worklog IS NULL OR json_valid(worklog))"
)

MIGRATIONS: list[str] = [
    SCHEMA_1,
    SCHEMA_2,
    SCHEMA_3,
    SCHEMA_4,
    TOOLS_SQL,
    CANVAS_SQL,
    FOLDERS_SQL,
    EFFORT_SQL,
    WORKLOG_SQL,
]

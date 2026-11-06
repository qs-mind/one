# qsone-cli

ONE without the screen: a thin client of the existing local HTTP routes. No AI or
quantity calculations are implemented here. Run from this checkout's `core/`:

```sh
/home/kareem/Work/qs-mind/one/core/.venv/bin/python -m qsone.cli --help
```

Use that interpreter with this worktree's working directory (or `PYTHONPATH=core`
from its root). No installation or new dependency is needed. `walk` lazily uses
PyYAML 6.0.3, already in `requirements.lock` (MIT).

## Session and isolation

`start` defaults to scripted AI, a free loopback port and a fresh temporary data
folder. It launches `python -m tests.bench` from this checkout's `core/`, with the
bench's in-memory key store and sample files. Its output says sample data.

```sh
python -m qsone.cli start
python -m qsone.cli --json project new 'Sample tender'
python -m qsone.cli files add PROJECT '/path/to/sample.xlsx'
python -m qsone.cli files report PROJECT
python -m qsone.cli ask PROJECT 'bench:boq Import the BOQ'
python -m qsone.cli card answer CARD keep
python -m qsone.cli boq show PROJECT
python -m qsone.cli costs
python -m qsone.cli stop
```

The project ID comes from `project new`, and the card ID from `ask`. The sample
folder is returned by `start`. Use a sentence after a bench keyword: the existing
bench language detector treats a bare keyword as Arabic, which can conflict with
the core's question-language check.

Global flags `--json`, `--lang en|ar`, and `--session PATH` work before or after
commands. The default session is `<temp>/qsone-cli-<uid>/session.json`, overridable
with `QSONE_CLI_SESSION`. Use a dedicated private parent directory (0700); the
session is atomically written with mode 0600. It contains the core bearer secret,
port, PID and process birth time, data folder, mode, and cached cards, **never an
AI key**. Keep it private. Linux `/proc` is required for owned-process stop checks.

Ports 1440 and 1442 are always refused. ONE's system data directory and all its
children are always refused, including explicit paths and symlinks. Explicit
`--data-dir` must be empty. Child processes receive an allowlist of OS environment
variables; inherited AI keys and bench network overrides are excluded.

`stop` signals only the exact owned launcher, data directory and process birth
identity. It retains the session if identity verification fails. Data and
`core.log` are retained for inspection; remove the throw-away directory yourself
when finished. `stop BRIEF` instead stops that Brief and keeps the session alive.

`attach --port P --secret-file PATH` connects to an existing core. Stopping an
attached session only forgets it. Attach cannot verify that server's AI mode or
data folder: use only a development core you isolated yourself. Walks treat an
attached session as real for cap enforcement.

## Real mode (opt-in; not used in tests)

`start --mode real` launches this checkout's `scripts/realapp/realcore.py`, **not**
the bench. It sets `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring`; the real
core keeps `keystore.json` in its private throw-away data directory, and uses
ONE's real search model. The launcher disables Claude Code and browser opening.

```sh
python -m qsone.cli start --mode real
python -m qsone.cli setup ai --provider google --model MODEL --key-file /private/provider.txt
python -m qsone.cli setup finish
python -m qsone.cli walk tests/walks/lahun.yaml --max-usd 3 --report /tmp/lahun-report.json
python -m qsone.cli stop
```

Provider checks and real AI cost money; only run with authorization. Keys are
read exclusively from `--key-file`, sent in the HTTP body, and never placed in
argv, the environment, CLI output or session JSON. A failed Google connection is
removed through the same route as the screen. `setup ai` returns the core's role
choices. `setup finish` records consent, language, and skips optional onboarding
steps (including usage sharing); it returns the resulting setup and roles.

## Commands

- `project new NAME`, `project list`, `project open ID`. Currency comes from the
  BOQ import, so there is no project `--currency` flag.
- `files add PROJECT PATH...`, `files report PROJECT`, `files list PROJECT`.
  Uploads read the input without modifying it. Reports cover the project's files.
- `file show PROJECT FILE [--sheet [NAME] | --page N]`: sheet view, page text, or
  page count when neither flag is given.
- `ask PROJECT|general TEXT`, `follow CHAT`: reply, progress/worklog, cards, review,
  status and recorded costs. A busy chat returns its Brief ID with exit status 1.
- `card answer ID CHOICE [--answer ID=VALUE ...] [--rows all|0,2]`,
  `card approve ID`: use cached BOQ meanings and all tickable rows by default.
  Questions require explicit answers; approve means `yes`. Stream replay does
  not reopen an answered card. A completed-between-requests Brief is read from
  stored chat messages.
- `stop BRIEF`, `steer BRIEF TEXT`.
- `boq show PROJECT` returns client BOQ summaries and source-bearing sheet views.
- `deliverable list PROJECT`, `deliverable show PROJECT ID`,
  `deliverable export PROJECT ID --format FORMAT --out PATH`.
- `changes accept|reject PROJECT DELIVERABLE [--ids ID,ID]`, `undo TOKEN`.
  Without IDs, the CLI fetches and submits all currently pending changes.
- `search PROJECT QUERY [--meaning|--words]` (`--words` maps to core `exact` mode).
- `number explain PROJECT NUMBER`, `costs [--brief BRIEF]`.

HTTP errors show core bilingual copy where available, never a raw request or
exception. Plain output selects the requested language and stamps its local core
source/time. JSON preserves the API's bilingual text, dates and source records.

## Walk format

A YAML document has `name`, optional `needs`, optional `max_usd` (default 3), and
`scripted` / `real` step lists. The session mode selects the list. Every missing
`needs` path causes `SKIPPED` and exit 0 before any step runs. Real tender files
are private, read-only inputs; no fixture copies are included.

Variables: `{samples}` is the session sample folder, `{test_files}` is the
nearest checkout ancestor's `docs/test-files` (or `QSONE_TEST_FILES`), and `{run}`
is a fresh suffix for repeatable project names. The supplied real paths resolve
under `/home/kareem/Work/qs-mind/one/docs/test-files` in this worktree.

```yaml
name: Sample scenario
max_usd: 3
scripted:
  - project: Sample {run}
  - files: ['{samples}/جدول كميات - عينة اختبار (sample BOQ).xlsx']
  - ask: 'bench:boq Import the BOQ'
    answer: {rows: keep}
  - boq: show
  - check: {boq_items: 4, boq_sections: 2, no_raw: true}
```

Steps are `project` (name), `files` (paths, followed by the free report), `ask`
(text, with optional `answer` rules by card kind), `card` (`kind`, `choice`,
optional `answers` and `rows`), `boq: show`, or `check` (mapping). An answer rule
can be a choice string or `{choice, answers, rows}`. Unknown cards are left pending
for an explicit subsequent `card` step; there is no implicit paid approval.

Checks: `reply_contains`, `reply_lacks` (scalar/list, Arabic digits normalized),
`no_raw` (32-hex IDs and the core's JSON detector), `cited` (`value`, zero-based
`file` index, plus `page` or `sheet`/`row`), `boq_items`, `boq_sections`,
`items_unchanged` (IDs compared with the first `boq` step), `card_meanings`
(column-to-meaning mapping), `max_usd` (latest Brief's own costs), and
`quantity_rows` (`first`, `last`, `column`, optional `sheet`/`file`). The last check
verifies Lahun rows 54–64 against their original D cells, with F empty and a
quantity sourced to D for every row. It fails rather than hiding a missing import.

Before each AI step and every five seconds while following (even without stream
heartbeats), the runner reads `/costs`. Month spend minus the initial baseline
at or above the cap stops the active Brief and marks remaining steps `NOT_RUN`.
New unpriced usage in real mode or unavailable cost records also stop it.
Cost reads have a five-second timeout. The final response is checked too.
This is a recorded-spend stop, not a reservation: an in-flight provider request
can finish above the threshold before its cost is recorded. The core's own caps
remain active as well. `--max-usd` overrides the YAML limit.

Reports contain each check's pass/fail, `/costs` tokens and prices, elapsed seconds,
and the source/time. `--report` writes the JSON; plain output presents the same
report. Exit codes: 0 pass/skip, 1 failed check/cap/command error, 2 invalid CLI
arguments. The three tender walks retain the approved known answers as test
expectations, not claims about a real run.

## Verification

From the worktree root:

```sh
/home/kareem/Work/qs-mind/one/core/.venv/bin/python -m pytest core/tests/test_cli.py
/home/kareem/Work/qs-mind/one/core/.venv/bin/python -m ruff check core
/home/kareem/Work/qs-mind/one/core/.venv/bin/python -m ruff format --check core
```

All CLI tests use scripted AI and free local ports. Real launcher selection is
inspected without launching real mode. No real provider is called.

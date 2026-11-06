# qsone-cli

ONE without the screen: a thin client of the existing local HTTP routes. No AI or
quantity calculations are implemented here. Run from this checkout's `core/`:

```sh
core/.venv/bin/python -m qsone.cli --help
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
`scripted` / `real` step lists. The session mode selects the list; an absent mode is skipped. Every missing
`needs` path causes `SKIPPED` and exit 0 before any step runs. Real tender files
are private, read-only inputs; no fixture copies are included.

Variables: `{samples}` is the session sample folder, `{test_files}` is the
nearest checkout ancestor's `docs/test-files` (or `QSONE_TEST_FILES`), and `{run}`
is a fresh suffix for repeatable project names. The supplied real paths resolve
under `docs/test-files` in this worktree.

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
New unpriced usage in real mode also stops it as CAP. An unavailable cost read
fails the current step and stops active real-AI work without asserting CAP; later
steps and walks can recover with fresh cost reads.
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
core/.venv/bin/python -m pytest core/tests/test_cli.py
core/.venv/bin/python -m ruff check core
core/.venv/bin/python -m ruff format --check core
```

All CLI tests use scripted AI and free local ports. Real launcher selection is
inspected without launching real mode. No real provider is called.

## Pre-contract CLI extension (6 November 2026)

Additional commands (shared `--json` and `--lang en|ar` still apply):

- `deliverable check P D` asks the core's Lead QS to submit the current Deliverable
  to the Checking QS through chat, then reads closeout. It reports failure if a
  settled reply did not record a check on the current saved version. A check can
  cost money; it does not grant sign-off or bypass blocking review comments.
- `deliverable signoff P D` uses the screen's Sign-off route. `show` now includes
  version history. Ordinary Sheet/Document exports follow `DRAFT_EXPORTS = True`:
  exports before Sign-off are allowed and marked «مسودة — غير معتمد» / "Draft — not
  signed off". The CLI adds no refusal. Pack exports have their own signed-only gate.
- `pack show P D`; `pack build P D --out FILE.pdf` invokes the screen's build step,
  then downloads the signed export. An unsigned pack can be previewed by the core
  but cannot be downloaded by this command. PDF results include actual page count
  and bookmark titles/page destinations read from the returned bytes.
- `compare P OLD_FILE NEW_FILE` preserves changed pages, word differences and
  pairing explanations from the core.
- `region add P F --page N --box x0,y0,x1,y1 COMMENT`; `region list P F` use file
  comments with the screen's region anchor. Coordinates are displayed PDF points.
- `file pdf P F --out FILE.pdf` uses the office conversion route; core bilingual
  LibreOffice refusals are preserved and a failed download leaves existing output
  untouched.
- `changes list P D` reads pending changes including old values and proposed ops.
- `costs --today` selects today's recorded cost/token fields; `--brief` remains.

Additional checks: `reply_not_contains` (`reply_lacks` remains), `reply_numbers`
(exact decimal tokens with Arabic digit normalization), `no_promise` (core truth
function), `deliverable` (kind/variant/title_contains and content),
`deliverable_numbers` (each expected value has a source), `boq_total` (a calculated
Deliverable total), `changes_count`, `export_ok` (`pages` is a minimum),
`pack_pages` (exact), `compare_pages` (exact changed new-page set), `max_steps`
(latest worklog snapshot), `max_input_tokens` (latest Brief's recorded inputs),
`rates_cited`, `boq_units`, `boq_sources`, `changes_target`, `calculated_numbers`,
`scan_report`, `ocr_boxes`, and `pack_integrity`. Item/change counts accept `{min: N}`.
`cited` requires the reply to name the expected page, DOCX paragraph, or sheet/row
(bare row for CSV) as well as finding the value at that location. A requested
column restricts evidence to that cell. Numeric matching is exact, including a
number followed by a sentence period. Check evaluation is pure; the runner fetches
source evidence separately before calling it.

New walk steps:

```yaml
- deliverable: {kind: sheet, variant: boq}
- check: {deliverable: {kind: sheet, variant: boq}, boq_total: '1810000'}
- command: [changes, list, '{project}', '{deliverable}']
- make: {source: '{samples}/../workspace/عرض أسعار المورد - عينة.pdf', page: 2}
- files: ['{revision}']
```

The number above is **sample data**, from the bench sample BOQ's four item amounts.
`command` reuses the CLI parser/adapters. Dynamic variables are `{project}`,
`{file0}` etc. in upload order, `{deliverable}`, `{undo}`, `{revision}`, and
`{scratch}`. `make` makes only a fixed SAMPLE REVISION text addition on one page,
writing a uniquely named copy in the run scratch folder; it never edits the input
and never executes YAML-provided Python. Scratch artifacts are retained for review.

`walk --all DIR --scripted-only --report /tmp/one-walks.json` runs YAML files in
filename order. A real/attached session is refused with `--scripted-only` (it never
silently labels a real provider scripted). A failed action invalidates its evidence; following checks fail until another
action succeeds. A failed check does not erase evidence for independent checks.
Subsequent actions continue. Set `stop_on_fail: true` on a step to stop that walk on failure (including a step inside a capability branch).
Later walks still run. Only confirmed recorded spending or unknown real-AI prices
produce CAP. Transient cost-read failures do not latch the folder budget.
The folder guard uses the sum of the YAML caps, or the smaller explicit `--max-usd`, in addition to each walk's own cap.
`--report` writes JSON and a sibling `.txt` report. `needs` may be a mapping with
separate `real` and `scripted` path lists, so missing private inputs do not skip
sample tests. These are recorded-spend caps; in-flight requests can overshoot.

### Scenario coverage and verification limits

The eleven requested walks have separate real and scripted branches. Each real
cap is $0.10 ($1.10 total); bench adds $0.10 to a folder run. Limits are not cost
forecasts. No real AI is used by CLI tests or scripted walks.

The scripted branches use fresh, labelled sample files and the bench model's
scripted tool calls. They exercise their own jobs: pricing sourced rates and
concrete-only changes/undo plus a letter (Lahun); ranked BOQ values and unchanged
items (SGH); cited conditions/PDF import (Brissa); PDF BOQ import; native XLS and
DOCX paragraph sources/conversion; pack proposal/accept/check/sign-off/build;
page revision comparison and region comments; CSV prices and sourced pricing;
Calc Engine estimates; conditions citations; and scan reporting/missing OCR.
They never read private tender fixtures. Sample numbers are not real prices.

`changes_target` requires exactly one pending rate change per matching concrete
item and rejects all other targets/operations. `calculated_numbers` requires each
expected number's calculation source and calculation identifier. `pack_integrity`
reads the actual export: exact bookmarks/destinations, one correct footer on every
page, identical duplicated content after stripping overlays, and the populated
ONEIntegritySeal signature field. Seal presence is not a cryptographic trust
verdict; core seal tests cover signature validity.

Known real assertions include Lahun's counts/total/D54–D64/pricing-sheet sources,
concrete-only rate-change targets and letter numbers; SGH's top five/division total
and M8–P8 breakdown sources; Brissa's cited tender terms; DOCX currency at paragraph
293; GASTAT September 2026 at CSV start line/row 1902 column H (record 952, with quoted newlines); and SCAD rebar at row 42.
The real pack asks for exactly a cover, two copies of the first form page and a
divider, with four named bookmarks, page numbers and the free seal; all are checked.

The supplied Mansoura summary is blank and Giza's printed total is not established.
Their total checks are deliberately omitted, documented in the walk's YAML comment.
No expected total is invented. Real benchmark-scope/range and item-cost-analysis
build-up expectations remain unestablished; scripted estimates/pricing exercise
those routes with labelled sample inputs instead. Real walks have not been run
with a paid provider, so passing scripted walks is not a certification of real-AI
accuracy on every tender. New dependencies: none.

A walk may explicitly use `review: close_fixed` after asking the Lead to address review
comments, accepting the linked Suggested changes, and requesting a fresh check. It closes
only Code C threads with an accepted change carrying their `comment_id` and a current
Code A/B check. It refuses unresolved comments; it never grants Sign-off.

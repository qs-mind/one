"""The tender plan as data (Phase 1, C2): the plan the Lead writes, the engineer approves once
and code then drives stage by stage.

- `model`: what the plan tools take, the checks a plan passes, and its estimate.
- `store`: the plan in Project Records, every state kept; what the routes and the driver call.
- `build`, `members`, `signoff`: the stored plan from the Lead's draft, its team, a stage's
  sign-off.
- `tool`: `tender_plan_write` and `tender_plan_change`, the Lead's tools.
- `routes`: rows 8 to 12 of the Phase 1 contract."""

# Lead mirror and save queue

**Status:** spec, 2026-11-15. Phase 1 and phase 2a (the copy when the ERP is away) built; the rest of phase 2 and phases 3 and 4 not started. This document is the living source of truth for
the feature; update it with every change.

## Why

Leads live on the ERP (india.teambackoffice.com, ERPNext `Lead` + TBO Smart). The hub reads and
writes them through `helpdesk/integrations/crm` on every screen, so the hub is only as fast and as
available as the ERP. The owner chose (2026-11-10) to keep the ERP as the **master** and give the
hub a **local mirror** for reads and a **save queue** for writes, so leads still open and changes
are not lost while the ERP is slow or down.

Not the goal: moving the master to the hub. Quotations, invoices, commission, call batches,
telephony, AI, the mobile app and the Lead Bank all work on the ERP's Lead.

## Rules

1. **The ERP wins.** The mirror is a copy; a conflict is settled by the ERP's version.
2. **No migration.** The mirror is filled by copying from the ERP; nothing is deleted or moved on
   the ERP, so no data can be lost. Throwing the mirror away and rebuilding it is always safe.
3. **Same visibility.** A person sees in the mirror exactly the leads the ERP would show them.
4. **Every save reaches the ERP or tells the person.** A queued save is visible ("Saving…, will
   send when the CRM is back") and a failed one is shown with its reason; none disappears silently.

**Divisions** (docs/divisions.md): the mirror holds only the CRM connection's leads. A person
whose active division has its own ERP site reads and writes there and never falls back to the
mirror (`api/leads.read_or_copy`).

## Phases

| Phase | What | Visible change |
| --- | --- | --- |
| 1 (built) | ERP change feed + hub mirror doctypes + initial and continuous sync + health page | None yet (mirror fills in the background) |
| 2a (built) | When the ERP can't answer, the Leads list (All, Mine) and a lead's page come from the mirror, read only, with a notice | Leads open when the ERP is down or being updated |
| 2b | Leads list, lead page and My leads read from the mirror first | Faster lists |
| 3 | Save queue: writes go to the ERP, or wait in the queue when it is down, and are replayed in order | Saving works through an outage |
| 4 | Overview, Daily report, Business and Today's calls from the mirror where it is safe | Faster dashboards |

## Phase 1 (built)

### ERP (tbo_smart, docs/hub-leads-api.md §2.32)

- **Change log** `TBO Lead Change` (lead, change_type, at). Written after the transaction commits
  (a rolled-back save leaves no row; a failure to write is logged and never breaks the save), by
  doc_events on: Lead (on_update, on_trash, after_rename: a merge logs the old name `Deleted` and
  the kept lead `Lead`), Comment (notes only), Event (Call or Event, by its participants), ToDo
  (Follow-up; also an assignment), TBO Call, File, TBO Call Batch (its items' leads), and, beyond
  the first plan, Quotation, TBO Proposal, TBO Lead Meeting and Opportunity (the lead's payload
  holds them). Contact numbers are child rows of the Lead, so they log as `Lead`. Not logged:
  emails and WhatsApp (the nightly comparison does not see them either: `modified` does not move;
  phase 2 refreshes a lead when it is opened). Pruned after 30 days, daily.
- `get_lead_changes(since, limit)`, `get_lead_index(after, limit)` (every lead by name with
  `modified`, for the backfill and the nightly comparison), `get_leads_bulk(names)` (at most 100:
  row, payload, owner, assignees, department; run as the integration user, so it reads every
  lead) and `get_mirror_scopes()`. All integration user only.
- **Visibility.** A per-lead user list would go stale when a team or a department head changes
  (the lead itself does not change), so each lead carries `owner`, `assignees` (ToDos not
  cancelled) and `department`, and each person's scope travels apart: `{all, team, departments}`.
  A person sees a lead when `all`, or its owner or an assignee is in `team` (themselves and their
  team in the sales hierarchy), or its department is one they head. This is exactly
  `tbo_smart.sales.permissions`; the ERP's tests check it against `frappe.has_permission` for a
  salesperson, one in the hierarchy, a team leader, a head and a manager. The payload leaves out
  what is about the person asking (`can_write`, `can_call`, `can_remove_numbers`, `can_merge`,
  `allowed_stages`); phase 2 must work those out per person.

### Hub (helpdesk)

- `HD Lead Mirror` (name = ERP lead name; module Helpdesk; System Manager and Agent Manager read,
  nobody writes by hand): lead_name, company_name, mobile_no, email_id, tbo_stage, status,
  lead_owner, department, product, temperature, score, source, industry, state, district,
  org_size, next_follow_up, last_call_result, erp_created, erp_modified, synced_at, `assignees`
  (child `HD Lead Mirror Assignee`), `list_row` (the ERP's list row, for the list's quotation and
  proposal summaries) and `payload` (the `get_lead` answer). A lead deleted or merged away on the
  ERP is deleted from the copy (no `deleted` flag), so counts compare directly.
- `HD Lead Sync State` (single): `enabled` (off by default), `since` (the ERP's clock), backfill
  status, last run, last successful sync, lag, last error, leads copied, the ERP's total at the
  last comparison, the last comparison and its result, and `scopes` (the ERP's per-person scopes,
  refreshed every sync).
- `helpdesk/lead_mirror.py`:
  - **`sync_lead_changes`, every minute** (cron): does nothing while off. Under a file lock
    (`locks/lead_mirror.lock`) so two runs never overlap (a run that finds it held returns at
    once). Refreshes the scopes, then reads the feed from `since` minus 60 seconds (so a change
    committed out of order is still read; copying a lead twice is harmless), pages of 500, fetches
    those leads in batches of 100 in the order they changed (each lead once, by its latest
    change), upserts by ERP name and deletes the ones the ERP says are missing. `since` moves on
    only after a batch is saved and committed. A failed batch leaves `since` where it was and is
    shown as the last error; a lead the ERP could not read keeps its old copy and is named in the
    error. Lag is the age of the newest change when it was copied.
  - **`backfill_lead_mirror`** (long queue, 4 h): started when the copy is turned on or rebuilt
    (and by a sync that finds no `since`, or a "Copying" status left by a run that died). Walks
    `get_lead_index` in pages of 1000, copies the leads missing or whose `modified` differs, drops
    copies the ERP does not have, then sets `since` to the ERP's clock at the walk's start. Rerun
    any time: it copies only what differs. The sync is paused (the lock) while it runs.
  - **`check_drift`, daily**: the same walk, without touching `since`; records the result.
- Settings → CRM → *Local copy of leads* (`LeadMirror.vue`, admins and managers): the on/off
  switch, a health line (leads copied, last sync, lag; the count moves while copying), the last
  error, the nightly result and **Rebuild copy** (clears the copy and backfills; refused while a
  run is in progress). API: `helpdesk.api.lead_mirror` (`get_health`, `set_enabled`, `rebuild`).
- Nothing reads the mirror in phase 1.

### Tests

`helpdesk/tests/test_lead_mirror.py` against `FakeLeadERP` (helpdesk/test_utils.py): backfill, its
paging and rerun, sync order, idempotency, deletes, paging, failure without moving `since`,
unreadable leads, scopes, the lock, lag, drift, the settings API and permissions.

## Phase 2a (built): the copy when the ERP is away

The ERP is still asked first on every request; nothing changes while it answers.

- `helpdesk.api.leads.read_or_copy`: when the ERP call fails as **unavailable** (unreachable,
  5xx, Frappe Cloud maintenance, a refused API key; not "TBO Smart too old", not a refusal of the
  person or the lead) and the copy is **ready**, the answer comes from `helpdesk/lead_mirror_read.py`
  and carries `from_copy: true` and `copied_at`. When the copy has no answer the ERP's error stands.
- **Ready** (`lead_mirror_read.ready`): the copy is on and its first full copy has finished
  (`since` is set). Not `last_synced_on`: an empty Datetime on a Single reads back as now.
- **Leads list** (`list_from_copy`, `list_copy`): the All and Mine tabs, with search (ID, name,
  company, mobile, email) and the filters the copy has columns for (stage, owner, department,
  source, temperature, industry, state, district, size, product, last call result), the last
  changed first. Any other tab or filter (Follow-up, Call today, Called, segment, an Overview
  number, reply class, Created by me, due dates) is the ERP's to work out, so it stays an error
  rather than a wrong list. A BD's Mine is the leads they own (the ERP also adds the ones they
  created; the copy has no column for that).
- **A lead's page** (`lead_copy`): the stored `get_lead` answer with `can_write`, `can_call`,
  `can_remove_numbers` and `can_merge` false and no `allowed_stages`. The page hides Edit and Log
  call; its other parts (documents, AI, WhatsApp) ask the ERP themselves and show their own
  "couldn't load" until it is back.
- **Visibility** (`scope_of`, `visible`): the person's scope from `HD Lead Sync State.scopes`:
  every lead, or the leads whose owner or an assignee is in their team, or whose department they
  head. Someone the ERP never listed gets no copy (the ERP's error stands).
- **On screen** (`LeadCopyNotice.vue`): "The CRM can't be reached right now. You're seeing the
  copy saved on …" with Try again, above the list and on the lead.
- Tests: `helpdesk/tests/test_lead_mirror_read.py`.
- **Needs** the copy switched on (Settings → CRM → Local copy of leads) and filled once. On
  2026-11-15 it was still off on the live hub.

## Phase 2b to 4

To be detailed when phase 1 is live and its lag and counts have been checked against the ERP.

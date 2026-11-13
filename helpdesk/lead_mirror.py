"""The hub's local copy of the ERP's leads (docs/lead-mirror.md, phase 1).

The ERP stays the master. This keeps `HD Lead Mirror` current from the ERP's change feed and
bulk read (TBO Smart's `hub_lead_mirror`, docs/hub-leads-api.md §2.32); nothing reads the copy
yet. Three jobs, one at a time (a file lock, so two never overlap):

- `sync_lead_changes`, every minute: read the changes since the last one, fetch those leads in
  batches of 100, and make or drop their copies, in the order they changed. `since` moves on only
  after a batch is saved, and starts a minute behind the last change so one committed out of
  order is still read (copying a lead twice is harmless).
- `backfill_lead_mirror`, when the copy is turned on or rebuilt: walks the ERP's index of every
  lead and copies the ones that are missing or differ. Run it again at any time; it only copies
  what differs.
- `check_drift`, daily: the same walk, which also drops copies of leads the ERP no longer has.
"""

import json
import os
from contextlib import contextmanager

import frappe
from filelock import FileLock, Timeout
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_site_path, now_datetime

from helpdesk.helpdesk.doctype.hd_lead_mirror.hd_lead_mirror import DOCTYPE as MIRROR
from helpdesk.helpdesk.doctype.hd_lead_mirror.hd_lead_mirror import HDLeadMirror
from helpdesk.integrations.crm.client import CRMClient, CRMError
from helpdesk.integrations.crm.leads import friendly_error

STATE = "HD Lead Sync State"
API = "tbo_smart.api.hub_lead_mirror"
OVERLAP_SECONDS = 60
CHANGES_PAGE = 500
BULK = 100
INDEX_PAGE = 1000
# a first copy of every lead takes a while; the long queue allows it
BACKFILL_TIMEOUT = 4 * 60 * 60
BACKFILL_WAIT = 120
BACKFILL_JOB = "helpdesk.lead_mirror.backfill_lead_mirror"
BACKFILL_JOB_ID = "lead_mirror_backfill"


def mirror_on() -> bool:
    return bool(
        frappe.db.get_single_value(STATE, "enabled")
        and frappe.db.get_single_value("HD CRM Settings", "enabled")
    )


@contextmanager
def single_flight(wait: float = 0):
    """Yields True while this process holds the mirror's lock, or False at once (or after
    `wait` seconds) when another run has it."""
    path = get_site_path("locks", "lead_mirror.lock")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lock = FileLock(path, timeout=wait)
    try:
        lock.acquire()
    except Timeout:
        yield False
        return
    try:
        yield True
    finally:
        lock.release()


def is_running() -> bool:
    """Whether a run holds the lock right now."""
    with single_flight() as free:
        return not free


def enqueue_backfill() -> None:
    frappe.enqueue(
        BACKFILL_JOB,
        queue="long",
        timeout=BACKFILL_TIMEOUT,
        job_id=BACKFILL_JOB_ID,
        deduplicate=True,
        enqueue_after_commit=True,
    )


def set_state(**values) -> None:
    frappe.db.set_single_value(STATE, values)


def same_time(first, second) -> bool:
    return bool(first and second) and get_datetime(first) == get_datetime(second)


class LeadMirrorSync:
    """One run against the ERP. `client` is the CRM connection (a fake in tests)."""

    def __init__(self, client=None):
        self.client = client or CRMClient.from_settings()

    def call(self, method: str, **params):
        return self.client.call(f"{API}.{method}", **params)

    # ---------- the three jobs ----------

    def catch_up(self) -> list[str]:
        """Copy every lead changed since the last run, oldest change first. Returns the leads
        the ERP would not give (each with its reason is in `last_error`)."""
        since = frappe.db.get_single_value(STATE, "since")
        cursor = self.shifted(since)
        newest = 0
        unread = []
        while True:
            feed = self.call("get_lead_changes", since=cursor, limit=CHANGES_PAGE)
            changes = feed["changes"]
            unread += self.apply([change["lead"] for change in changes])
            if changes:
                cursor = feed["next_since"]
                fresh = [
                    c
                    for c in changes
                    if not since or get_datetime(c["at"]) > get_datetime(since)
                ]
                if fresh:
                    newest = max(newest, self.age(feed["now"], fresh[-1]["at"]))
                # only now, with the batch saved, does the feed's position move on
                set_state(since=str(cursor))
                frappe.db.commit()  # nosemgrep
            if not feed["more"]:
                break
        set_state(lag_seconds=newest)
        return unread

    def reconcile(self) -> dict:
        """Walk the ERP's index of every lead: copy those missing or different, drop the copies
        the ERP no longer has. Returns {started (the ERP's clock when the walk began, where
        the change feed picks up), total, copied, removed, unread}."""
        seen, copied, unread = set(), 0, []
        after, started, total = None, None, 0
        while True:
            page = self.call("get_lead_index", after=after, limit=INDEX_PAGE)
            if started is None:
                started, total = page["now"], page["total"]
            names = [row["name"] for row in page["leads"]]
            have = self.copies_of(names)
            stale = [
                row["name"]
                for row in page["leads"]
                if not same_time(have.get(row["name"]), row["modified"])
            ]
            unread += self.apply(stale)
            copied += len(stale)
            seen.update(names)
            frappe.db.commit()  # nosemgrep
            after = page["next_after"]
            if not page["more"]:
                break
        Copy = frappe.qb.DocType(MIRROR)
        gone = set(frappe.qb.from_(Copy).select(Copy.name).run(pluck=True)) - seen
        for name in gone:
            HDLeadMirror.remove(name)
        frappe.db.commit()  # nosemgrep
        return {
            "started": started,
            "total": total,
            "copied": copied,
            "removed": len(gone),
            "unread": unread,
        }

    # ---------- what each job does ----------

    def run_sync(self) -> list[str] | None:
        if frappe.db.get_single_value(STATE, "backfill_status") == "Copying":
            # the lock was free, so that copy died: start it again
            set_state(backfill_status="Idle", since="")
        if not frappe.db.get_single_value(STATE, "since"):
            enqueue_backfill()
            return None
        self.refresh_scopes()
        return self.catch_up()

    def run_backfill(self) -> list[str]:
        set_state(backfill_status="Copying")
        frappe.db.commit()  # nosemgrep
        self.refresh_scopes()
        result = self.reconcile()
        # the changes from the walk's start on are the feed's to catch
        set_state(
            since=str(result["started"]),
            erp_total=result["total"],
            backfill_status="Idle",
            lag_seconds=0,
        )
        return result["unread"]

    def run_drift_check(self) -> list[str]:
        result = self.reconcile()
        set_state(
            last_compared_on=now_datetime(),
            erp_total=result["total"],
            compare_result=_(
                "{0} leads on the ERP: {1} copied again, {2} copies dropped."
            ).format(result["total"], result["copied"], result["removed"]),
        )
        return result["unread"]

    # ---------- the parts ----------

    def apply(self, names: list[str]) -> list[str]:
        """Bring the copies of `names` up to date, in the order given, 100 at a time. Returns
        the leads the ERP could not read (they keep their old copy)."""
        unread = []
        for start in range(0, len(names), BULK):
            answer = self.call(
                "get_leads_bulk", post=True, names=names[start : start + BULK]
            )
            for entry in answer["leads"]:
                HDLeadMirror.upsert(entry)
            for name in answer["missing"]:
                HDLeadMirror.remove(name)
            unread += [f"{name}: {why}" for name, why in answer["errors"].items()]
            frappe.db.commit()  # nosemgrep
        return unread

    @staticmethod
    def copies_of(names: list[str]) -> dict:
        """{lead: when the copy says the ERP last modified it} for the leads copied."""
        if not names:
            return {}
        Copy = frappe.qb.DocType(MIRROR)
        return dict(
            frappe.qb.from_(Copy)
            .select(Copy.name, Copy.erp_modified)
            .where(Copy.name.isin(names))
            .run()
        )

    def refresh_scopes(self) -> None:
        answer = self.call("get_mirror_scopes")
        set_state(scopes=json.dumps(answer["scopes"]), scopes_synced_on=now_datetime())

    @staticmethod
    def shifted(since: str | None) -> str | None:
        return (
            str(add_to_date(get_datetime(since), seconds=-OVERLAP_SECONDS))
            if since
            else None
        )

    @staticmethod
    def age(now, at) -> int:
        return max(int((get_datetime(now) - get_datetime(at)).total_seconds()), 0)


# ---------- the jobs the scheduler and the queue run ----------


def finish(error: str | None = None, **values) -> None:
    set_state(
        last_run=now_datetime(),
        last_error=(error or "")[:1000],
        **({} if error else {"last_synced_on": now_datetime()}),
        **values,
    )
    set_state(leads_mirrored=frappe.db.count(MIRROR))
    frappe.db.commit()  # nosemgrep


def failure_text(error: Exception, client=None) -> str:
    if isinstance(error, CRMError):
        return str(friendly_error(error, client)) if client else str(error)
    return f"{type(error).__name__}: {error}"


def unread_text(unread: list[str]) -> str | None:
    if not unread:
        return None
    return _(
        "{0} leads could not be read on the ERP, so they keep their old copy: {1}"
    ).format(len(unread), "; ".join(unread[:5]))


def run_locked(title: str, job, wait: float = 0, **after_failure) -> None:
    """`job(sync)` (one of LeadMirrorSync's run_* methods) alone, with the result recorded on
    the state. A failure is logged and shown in the health line; the next run tries again."""
    with single_flight(wait) as free:
        if not free:
            return
        client = None
        try:
            client = CRMClient.from_settings()
            unread = job(LeadMirrorSync(client))
            if unread is not None:
                finish(unread_text(unread))
        except Exception as error:  # noqa: BLE001 - recorded and retried, never raised at the scheduler
            frappe.db.rollback()
            frappe.log_error(title=f"Lead mirror: {title} failed")
            finish(failure_text(error, client), **after_failure)


def sync_lead_changes() -> None:
    """Scheduler, every minute."""
    if mirror_on():
        run_locked("sync", LeadMirrorSync.run_sync)


def backfill_lead_mirror() -> None:
    """Queue (long): the first copy of every lead, or a rebuild; safe to run again."""
    if mirror_on():
        run_locked(
            "backfill",
            LeadMirrorSync.run_backfill,
            wait=BACKFILL_WAIT,
            backfill_status="Idle",
        )


def check_drift() -> None:
    """Scheduler, daily: compare the copy with the ERP's index and fix what differs."""
    if mirror_on() and frappe.db.get_single_value(STATE, "since"):
        run_locked("comparison", LeadMirrorSync.run_drift_check)

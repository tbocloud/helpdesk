"""Copies each data source's leads into HD CRM Report Lead and its organisation into
HD CRM Org Unit, for the CRM dashboards (docs/crm-dashboard.md).

The source stays the master: the copy holds only the mapped fields, and a full sync drops the
leads the source no longer has. One run per source at a time (a file lock), so a sync and a
recount never overwrite each other's rows.

- `sync_due_sources`, every 15 minutes: queues each enabled source whose interval has passed.
  A run reads the leads changed since the last one (a minute of overlap, so a change saved
  out of order is still read), or every lead when it is a full one.
- `full_sync_all`, daily: every lead of every enabled source, which also drops deleted leads.
- `recompute_source`, after a status mapping, rate, unit or relationship changes: counts the
  copied leads again without reading the source.
"""

import json
from datetime import date, datetime

import frappe
from frappe import _
from frappe.utils import add_to_date, flt, get_datetime, getdate, now_datetime
from frappe.utils.background_jobs import is_job_enqueued
from frappe.utils.synchronization import filelock

from helpdesk.crm_dashboard.registry import CLOSED, ORG_LEVELS, UNIT_PARENTS, UNIT_TYPES
from helpdesk.helpdesk.doctype.hd_crm_report_lead.hd_crm_report_lead import COLUMNS
from helpdesk.helpdesk.doctype.hd_crm_report_lead.hd_crm_report_lead import (
    DOCTYPE as REPORT_LEAD,
)
from helpdesk.helpdesk.doctype.hd_crm_report_lead.hd_crm_report_lead import (
    HDCRMReportLead,
)
from helpdesk.integrations.crm.client import CRMError

SOURCE = "HD CRM Source"
UNIT = "HD CRM Org Unit"
JOB = "helpdesk.crm_dashboard.sync.run_job"
PAGE = 500
OVERLAP_SECONDS = 60
JOB_TIMEOUT = 60 * 60
# a recount waits this long for a running sync of the same source to finish
LOCK_WAIT = 15 * 60
INTERVAL_MINUTES = {"15 minutes": 15, "Hourly": 60, "Every 6 hours": 360, "Daily": 1440}
# a tick is every 15 minutes; a run due a little after it waits for the next one otherwise
SLACK_MINUTES = 2
# ERPNext's own records, read when the source has them: {unit type: (doctype, fields)}
ORG_DOCTYPES = {
    "Company": ("Company", ["name"]),
    "Branch": ("Branch", ["name"]),
    "Department": ("Department", ["name", "department_name", "company"]),
    "Employee": (
        "Employee",
        ["name", "employee_name", "user_id", "company", "branch", "department"],
    ),
}


# ---------- scheduling ----------


def job_id(source: str, kind: str) -> str:
    """One job id per source and kind (sync, full, recount): a full read asked for while a
    sync runs is queued, never swallowed by it. The file lock runs them one at a time."""
    return f"crm_dashboard::{kind}::{source}"


def enqueue_sync(source: str, full: bool = False) -> None:
    frappe.enqueue(
        JOB,
        queue="long",
        timeout=JOB_TIMEOUT,
        job_id=job_id(source, "full" if full else "sync"),
        deduplicate=True,
        enqueue_after_commit=True,
        source=source,
        full=full,
    )


def enqueue_recompute(source: str) -> None:
    frappe.enqueue(
        JOB,
        queue="long",
        timeout=JOB_TIMEOUT,
        job_id=job_id(source, "recount"),
        deduplicate=True,
        enqueue_after_commit=True,
        source=source,
        fetch=False,
    )


def is_syncing(source: str) -> bool:
    return any(is_job_enqueued(job_id(source, kind)) for kind in ("sync", "full"))


def sync_due_sources() -> None:
    """Every 15 minutes: queue the enabled sources whose interval has passed. A failed run
    keeps its last good time, so it is tried again at the next tick."""
    now = now_datetime()
    for source in frappe.qb.get_query(
        SOURCE,
        fields=["name", "sync_every", "last_synced_on"],
        filters={"enabled": 1},
    ).run(as_dict=True):
        minutes = INTERVAL_MINUTES.get(source.sync_every, 60) - SLACK_MINUTES
        if (
            not source.last_synced_on
            or add_to_date(source.last_synced_on, minutes=minutes) <= now
        ):
            enqueue_sync(source.name)


def full_sync_all() -> None:
    """Daily: every lead of every enabled source, which drops the ones deleted there."""
    for name in frappe.qb.get_query(
        SOURCE, fields=["name"], filters={"enabled": 1}
    ).run(pluck=True):
        enqueue_sync(name, full=True)


def run_job(source: str, full: bool = False, fetch: bool = True) -> None:
    """The queued job: a sync (reads the source) or a recount (doesn't)."""
    with filelock(f"crm_dashboard_{frappe.scrub(source)}", timeout=LOCK_WAIT):
        if not frappe.db.exists(SOURCE, source):
            return
        sync = SourceSync(frappe.get_doc(SOURCE, source))
        if fetch:
            sync.run(full=full)
        else:
            sync.recompute()


def recompute_source(source: str) -> None:
    """Count the copied leads again now, e.g. right after the mapping changed in a test."""
    run_job(source, fetch=False)


# ---------- one source ----------


class SourceSync:
    """One run for one source. `client` is its connection (a fake in tests); a recount
    never opens it."""

    def __init__(self, source, client=None):
        self.source = source
        self._client = client

    @property
    def client(self):
        if self._client is None:
            self._client = self.source.client()
        return self._client

    def run(self, full: bool = False) -> int:
        """Read the leads, add the units they mention, count them again. Returns how many
        leads the copy holds. A failure is recorded on the source, never raised: the next
        tick tries again."""
        full = full or not self.source.sync_cursor
        try:
            leads = self.read_leads(full)
            units_changed = self.sync_units(leads)
            # a new unit or parent can move any lead: then every lead is counted again
            only = None if full or units_changed else [lead["name"] for lead in leads]
            copied = self.recompute(leads, drop_missing=full, only=only)
        except Exception as e:
            frappe.db.rollback()
            self.record_failure(e)
            return 0
        self.record_success(leads, copied, full)
        return copied

    def read_leads(self, full: bool) -> list[dict]:
        filters = []
        if not full:
            since = add_to_date(
                get_datetime(self.source.sync_cursor), seconds=-OVERLAP_SECONDS
            )
            filters = [["modified", ">=", str(since)]]
        fields = self.source.fields_to_read()
        leads, start = [], 0
        while True:
            page = self.client.get_page(
                self.source.lead_doctype, fields, filters, start=start, page_length=PAGE
            )
            leads += page
            if len(page) < PAGE:
                return leads
            start += PAGE

    # ---------- the organisation ----------

    def sync_units(self, leads: list[dict]) -> bool:
        """Add the units the source's ERPNext records and these leads name, top down so a
        unit's parent exists before it. Never changes what an admin set: only empty fields
        are filled, and nothing is switched off. Returns whether any unit was added or
        changed."""
        found = self.remote_units()
        for unit_type, units in self.units_on_leads(leads).items():
            for unit_name, values in units.items():
                # the source's own record wins; the lead fills only what it leaves empty
                merged = found[unit_type].setdefault(unit_name, {})
                merged.pop("only_if_on_leads", None)
                for key, value in values.items():
                    if not merged.get(key):
                        merged[key] = value
        existing = {
            (u.unit_type, u.unit_name): u
            for u in frappe.qb.get_query(
                UNIT,
                fields=["name", "unit_type", "unit_name"],
                filters={"source": self.source.name},
            ).run(as_dict=True)
        }
        changed = False
        for unit_type in UNIT_TYPES.values():
            for unit_name, values in found[unit_type].items():
                changed |= self.save_unit(
                    unit_type, unit_name, values, existing.get((unit_type, unit_name))
                )
        return changed

    def remote_units(self) -> dict[str, dict]:
        """{unit type: {unit name: values}} from ERPNext's Company, Branch, Department and
        Employee on the source; a doctype it doesn't have (or may not read) is skipped."""
        found: dict[str, dict] = {t: {} for t in UNIT_TYPES.values()}
        by_user = not self.source.employee_field
        for unit_type, (doctype, fields) in ORG_DOCTYPES.items():
            try:
                records = self.client.get_list(doctype, fields)
            except CRMError:
                continue
            for record in records:
                if unit_type == "Employee":
                    # leads name a salesperson by their owner's email unless an employee
                    # field is mapped; only those on leads become units
                    key = record.get("user_id") if by_user else record.get("name")
                    if key:
                        found["Employee"][key] = {
                            "label": record.get("employee_name"),
                            "user": record.get("user_id"),
                            "company": record.get("company"),
                            "branch": record.get("branch"),
                            "department": record.get("department"),
                            "only_if_on_leads": True,
                        }
                else:
                    found[unit_type][record["name"]] = {
                        "label": record.get("department_name"),
                        "company": record.get("company"),
                    }
        return found

    def units_on_leads(self, leads: list[dict]) -> dict[str, dict]:
        """{unit type: {unit name: values}} for every org value on these leads, each with
        the closest parent the lead carries next to it (the first lead seen decides)."""
        mapping = self.source.field_map()
        fields = {
            "company": mapping.get("company_field"),
            "branch": mapping.get("branch_field"),
            "department": mapping.get("department_field"),
            "team": mapping.get("team_field"),
            "employee": mapping.get("employee_field") or mapping.get("owner_field"),
        }
        found: dict[str, dict] = {t: {} for t in UNIT_TYPES.values()}
        if self.source.company_label:
            found["Company"][self.source.company_label] = {}
        for lead in leads:
            values = {lvl: text(lead.get(f)) if f else "" for lvl, f in fields.items()}
            for level in ORG_LEVELS:
                if not values[level]:
                    continue
                parents = UNIT_PARENTS[UNIT_TYPES[level]]
                closest = next((p for p in reversed(parents) if values[p]), None)
                found[UNIT_TYPES[level]].setdefault(
                    values[level], {closest: values[closest]} if closest else {}
                )
        return found

    def save_unit(self, unit_type: str, unit_name: str, values: dict, existing) -> bool:
        """Add or fill one unit; returns whether it was saved."""
        if existing is None and values.get("only_if_on_leads"):
            return False
        doc = (
            frappe.get_doc(UNIT, existing.name)
            if existing
            else frappe.get_doc(
                {
                    "doctype": UNIT,
                    "source": self.source.name,
                    "unit_type": unit_type,
                    "unit_name": unit_name,
                    "origin": "Synced",
                }
            )
        )
        before = doc.as_dict()
        if values.get("label") and doc.label in (None, "", unit_name):
            doc.label = values["label"]
        if (
            values.get("user")
            and not doc.user
            and frappe.db.exists("User", values["user"])
        ):
            doc.user = values["user"]
        for level in UNIT_PARENTS[unit_type]:
            if (
                values.get(level)
                and not doc.get(level)
                and self.has_unit(level, values[level])
            ):
                doc.set(level, values[level])
        if existing and all(
            doc.get(k) == before.get(k) for k in ("label", "user", *ORG_LEVELS[:-1])
        ):
            return False
        doc.flags.from_sync = True
        doc.flags.ignore_permissions = True
        try:
            doc.save()
        except frappe.ValidationError:
            # parents that disagree: keep what it had, or a new unit's closest parent
            # alone (the ones above fill from it)
            frappe.clear_last_message()
            closest = next(
                (lvl for lvl in reversed(UNIT_PARENTS[unit_type]) if doc.get(lvl)),
                None,
            )
            for level in UNIT_PARENTS[unit_type]:
                keep = before.get(level) if existing else None
                doc.set(level, keep or (doc.get(level) if level == closest else ""))
            doc.save()
        return True

    def has_unit(self, level: str, unit_name: str) -> bool:
        return bool(
            frappe.db.exists(
                UNIT,
                {
                    "source": self.source.name,
                    "unit_type": UNIT_TYPES[level],
                    "unit_name": unit_name,
                },
            )
        )

    # ---------- counting ----------

    def recompute(
        self,
        fetched: list[dict] | None = None,
        drop_missing: bool = False,
        only: list[str] | None = None,
    ) -> int:
        """Work out the copied leads' columns again from their raw fields (with `fetched`
        replacing the ones just read) and the units as they are now: every lead, or with
        `only` just those. Only rows that change are written. With `drop_missing`, the
        copies of leads not in `fetched` go. Returns how many leads the copy holds."""
        filters = {"source": self.source.name}
        if only is not None:
            if not only:
                return self.copied()
            filters["remote_name"] = ["in", only]
        stored = frappe.qb.get_query(
            REPORT_LEAD, fields=list(COLUMNS), filters=filters
        ).run(as_dict=True)
        old = {row.remote_name: row for row in stored}
        raws = {name: json.loads(row.raw or "{}") for name, row in old.items()}
        for lead in fetched or []:
            raws[lead["name"]] = lead
        missing = set()
        if drop_missing:
            missing = set(old) - {lead["name"] for lead in fetched or []}
            for name in missing:
                raws.pop(name, None)
        builder = RowBuilder(self.source)
        changed = []
        for name, raw in raws.items():
            row = builder.build(name, raw)
            if name not in old or same_row(old[name]) != same_row(row):
                changed.append(row)
        HDCRMReportLead.write(changed)
        HDCRMReportLead.remove(self.source.name, sorted(missing))
        return self.copied()

    def copied(self) -> int:
        return frappe.db.count(REPORT_LEAD, {"source": self.source.name})

    # ---------- the outcome ----------

    def record_success(self, leads: list[dict], copied: int, full: bool) -> None:
        newest = max((lead.get("modified") or "" for lead in leads), default="")
        values = {
            "last_synced_on": now_datetime(),
            "last_sync_status": "OK",
            "last_error": "",
            "leads_synced": copied,
            "sync_cursor": max(newest, self.source.sync_cursor or ""),
        }
        if full:
            values["last_full_sync_on"] = values["last_synced_on"]
        self.source.db_set(values, update_modified=False)
        # the job's work is done: keep it even if something after it in the job fails
        frappe.db.commit()  # nosemgrep

    def record_failure(self, error: Exception) -> None:
        message = error.user_message if isinstance(error, CRMError) else ""
        message = message or str(error) or error.__class__.__name__
        first = self.source.last_sync_status != "Failed"
        self.source.db_set(
            {"last_sync_status": "Failed", "last_error": message[:500]},
            update_modified=False,
        )
        if first:
            # once per outage, so a site that is down doesn't fill the Error Log
            frappe.log_error(
                title=_("CRM dashboard sync failed: {0}").format(self.source.name)
            )
        # the failure must stay visible in Settings although the job's work rolled back
        frappe.db.commit()  # nosemgrep


class RowBuilder:
    """Turns one lead's raw fields into the columns the dashboards count by."""

    def __init__(self, source):
        self.source = source
        self.fields = source.field_map()
        self.categories = source.categories()
        self.rate = flt(source.exchange_rate) or 1
        self.units = {
            (u.unit_type, u.unit_name): u
            for u in frappe.qb.get_query(
                UNIT,
                fields=["unit_type", "unit_name", "is_active", *ORG_LEVELS[:-1]],
                filters={"source": source.name},
            ).run(as_dict=True)
        }

    def build(self, name: str, raw: dict) -> dict:
        owner = self.value(raw, "owner_field")
        dims = {
            "company": self.value(raw, "company_field"),
            "branch": self.value(raw, "branch_field"),
            "department": self.value(raw, "department_field"),
            "team": self.value(raw, "team_field"),
            "employee": self.value(raw, "employee_field") or owner,
        }
        self.derive(dims)
        status = self.value(raw, "status_field")
        category = self.categories.get(
            (dims["company"], status)
        ) or self.categories.get(("", status), "")
        created = self.date(raw, "created_field")
        # a closing date counts only on a closed lead, and not before it was created;
        # days to close is 0 otherwise (an Int column can't be empty), and is read only
        # where closed_on is set
        closed = self.date(raw, "closing_date_field")
        if not (created and closed and closed >= created and category in CLOSED):
            closed = None
        closing_days = (closed - created).days if closed else 0
        return {
            "source": self.source.name,
            "remote_name": name,
            "excluded": int(self.has_inactive_unit(dims)),
            **dims,
            "lead_owner": owner,
            "status": status,
            "category": category,
            "lead_source": self.value(raw, "source_field"),
            "expected_revenue": self.money(raw, "expected_revenue_field"),
            "won_value": self.money(raw, "won_value_field"),
            "created_on": created,
            "created_month": created.strftime("%Y-%m") if created else "",
            "closed_on": closed,
            "closing_days": closing_days,
            "remote_modified": get_datetime(raw["modified"])
            if raw.get("modified")
            else None,
            "raw": json.dumps(raw, sort_keys=True, default=str),
        }

    def derive(self, dims: dict) -> None:
        """Fill the levels the lead doesn't carry from the units below them, closest first:
        an employee's team, then that team's department, its branch, its company. Leads with
        no company at all go under the source's company."""
        for level in reversed(ORG_LEVELS):
            unit = (
                self.units.get((UNIT_TYPES[level], dims[level]))
                if dims[level]
                else None
            )
            if not unit:
                continue
            for upper in UNIT_PARENTS[UNIT_TYPES[level]]:
                if not dims[upper] and unit.get(upper):
                    dims[upper] = unit[upper]
        dims["company"] = dims["company"] or (self.source.company_label or "")

    def has_inactive_unit(self, dims: dict) -> bool:
        for level in ORG_LEVELS:
            unit = (
                self.units.get((UNIT_TYPES[level], dims[level]))
                if dims[level]
                else None
            )
            if unit and not unit.is_active:
                return True
        return False

    def value(self, raw: dict, target: str) -> str:
        field = self.fields.get(target)
        return text(raw.get(field)) if field else ""

    def money(self, raw: dict, target: str) -> float:
        field = self.fields.get(target)
        return flt(raw.get(field)) * self.rate if field else 0.0

    def date(self, raw: dict, target: str) -> date | None:
        value = self.value(raw, target)
        if not value:
            return None
        try:
            return getdate(value)
        except Exception:
            return None


def text(value) -> str:
    return "" if value is None else str(value).strip()


def same_row(row) -> tuple:
    """A row's columns in a form that compares equal whether read back or just built."""

    def plain(value):
        if value is None or value == "":
            return ""
        if isinstance(value, datetime):
            return value.replace(microsecond=0).isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, int | float) or type(value).__name__ == "Decimal":
            return round(float(value), 4)
        return str(value)

    return tuple(plain(row.get(c)) for c in COLUMNS)

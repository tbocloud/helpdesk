# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from helpdesk.crm_dashboard.registry import (
    CATEGORIES,
    FIELD_TYPES,
    REQUIRED_FIELDS,
    mapped_fields,
)
from helpdesk.integrations.crm.client import CRMClient, CRMError

DOCTYPE = "HD CRM Source"
FIELDNAME = re.compile(r"^[a-z_][a-z0-9_]*$")
# changing these makes every copied lead stale: they are read again in full
READ_FIELDS = (
    "use_crm_connection",
    "site_url",
    "api_key",
    "lead_doctype",
    *mapped_fields(),
)
# changing these only changes how the copied leads are counted: worked out again locally
COUNT_FIELDS = ("company_label", "currency", "exchange_rate", "enabled")


class HDCRMSource(Document):
    """One company's (or one site's) leads for the CRM dashboards: where to read them, which of
    their fields mean what, how their statuses count, and how often to copy them
    (docs/crm-dashboard.md)."""

    def validate(self):
        self.validate_connection()
        self.validate_mapping()
        self.validate_status_map()
        self.validate_money()

    def on_update(self):
        self.refresh_copies()

    def on_trash(self):
        units = self.unit_names()
        self.validate_unused(units)
        self.delete_copies()

    # ---------- validation ----------

    def validate_connection(self):
        if self.use_crm_connection:
            self.validate_crm_connection()
        else:
            self.validate_own_connection()

    def validate_crm_connection(self):
        other = frappe.db.get_value(
            DOCTYPE, {"use_crm_connection": 1, "name": ("!=", self.name)}
        )
        if other:
            frappe.throw(
                _(
                    "{0} already reads the CRM connection. One data source per site, so its leads aren't counted twice."
                ).format(other)
            )
        settings = frappe.get_cached_doc("HD CRM Settings")
        if not (settings.site_url and settings.api_key):
            frappe.throw(_("Set up the CRM connection in Settings → CRM first."))
        # the connection's own key is used; nothing is kept twice
        self.site_url = ""
        self.api_key = ""

    def validate_own_connection(self):
        self.site_url = (self.site_url or "").strip().rstrip("/")
        self.api_key = (self.api_key or "").strip()
        if not re.match(r"^https?://[^/\s]+", self.site_url):
            frappe.throw(
                _("Type the site's full address, e.g. https://erp.example.com.")
            )
        if not self.api_key:
            frappe.throw(_("Add the API key of a user on {0}.").format(self.site_url))
        if not (self.api_secret or self.stored_secret()):
            frappe.throw(_("Add the API secret that goes with the key."))
        self.validate_site_is_new()

    def validate_site_is_new(self):
        crm_site = (
            frappe.db.get_single_value("HD CRM Settings", "site_url") or ""
        ).rstrip("/")
        if crm_site and crm_site == self.site_url:
            frappe.throw(
                _(
                    "{0} is the CRM connection's site. Switch on Use the CRM connection instead."
                ).format(self.site_url)
            )
        other = frappe.db.get_value(
            DOCTYPE,
            {
                "site_url": ("in", (self.site_url, self.site_url + "/")),
                "name": ("!=", self.name),
            },
        )
        if other:
            frappe.throw(
                _("{0} already reads {1}, so its leads would be counted twice.").format(
                    other, self.site_url
                )
            )

    def stored_secret(self) -> str | None:
        if self.is_new():
            return None
        return self.get_password("api_secret", raise_exception=False)

    def validate_mapping(self):
        fields = mapped_fields()
        used: dict[str, list[str]] = {}
        for target in fields:
            value = (self.get(target) or "").strip()
            self.set(target, value)
            if not value:
                continue
            if not FIELDNAME.match(value):
                frappe.throw(
                    _("{0}: {1} isn't a field name.").format(
                        fields[target]["label"], value
                    )
                )
            used.setdefault(value, []).append(target)
        for target in REQUIRED_FIELDS:
            if not self.get(target):
                frappe.throw(
                    _("Pick the field that holds the {0}.").format(
                        fields[target]["label"].lower()
                    )
                )
        for value, targets in used.items():
            if len(targets) > 1 and not self.may_share(targets):
                frappe.throw(
                    _("{0} can't be both the {1} and the {2}.").format(
                        value,
                        fields[targets[0]]["label"].lower(),
                        fields[targets[1]]["label"].lower(),
                    )
                )

    @staticmethod
    def may_share(targets: list[str]) -> bool:
        """A salesperson is often their leads' owner, and some sites keep one amount that
        is the expected revenue until the lead is won; those pairs may share a field."""
        pairs = (
            {"employee_field", "owner_field"},
            {"expected_revenue_field", "won_value_field"},
        )
        return any(set(targets) <= pair for pair in pairs)

    def validate_status_map(self):
        seen = set()
        for row in self.status_map:
            row.status = (row.status or "").strip()
            row.company = (row.company or "").strip()
            if not row.status:
                frappe.throw(_("Row {0}: type the lead status.").format(row.idx))
            if row.category not in CATEGORIES:
                frappe.throw(
                    _("Row {0}: pick a reporting category for {1}.").format(
                        row.idx, row.status
                    )
                )
            key = (row.company, row.status)
            if key in seen:
                frappe.throw(
                    _("{0} is mapped twice for {1}. Keep one row.").format(
                        row.status, row.company
                    )
                    if row.company
                    else _("{0} is mapped twice. Keep one row.").format(row.status)
                )
            seen.add(key)

    def validate_money(self):
        reporting = frappe.db.get_single_value("HD CRM Settings", "dashboard_currency")
        if reporting and self.currency == reporting:
            self.exchange_rate = 1
        if flt(self.exchange_rate) <= 0:
            frappe.throw(
                _("Type what one {0} is worth in {1}.").format(
                    self.currency, reporting or _("the reporting currency")
                )
            )

    def check_remote_fields(self, remote_fields: list[dict]) -> list[str]:
        """What's wrong with the mapping on the source's own lead fields: a field it doesn't
        have, or one of the wrong type. Empty when the mapping fits."""
        by_name = {f["fieldname"]: f for f in remote_fields}
        problems = []
        for target, meta in mapped_fields().items():
            value = self.get(target)
            if not value:
                continue
            field = by_name.get(value)
            if not field:
                problems.append(
                    _("{0}: {1} has no field {2}.").format(
                        meta["label"], self.lead_doctype, value
                    )
                )
            elif field.get("fieldtype") not in FIELD_TYPES[meta["kind"]]:
                problems.append(
                    _("{0}: {1} is a {2} field; pick one of type {3}.").format(
                        meta["label"],
                        value,
                        field.get("fieldtype"),
                        ", ".join(sorted(FIELD_TYPES[meta["kind"]])),
                    )
                )
        return problems

    # ---------- after a change ----------

    def refresh_copies(self):
        from helpdesk.crm_dashboard.sync import enqueue_recompute, enqueue_sync

        if self.changed(*READ_FIELDS):
            # the copies hold the old fields: read every lead again
            self.db_set("sync_cursor", "", update_modified=False)
            if self.enabled:
                enqueue_sync(self.name, full=True)
        elif self.changed(*COUNT_FIELDS) or self.status_map_changed():
            enqueue_recompute(self.name)

    def changed(self, *fields: str) -> bool:
        before = self.get_doc_before_save()
        if not before:
            return False
        return any((before.get(f) or "") != (self.get(f) or "") for f in fields)

    def status_map_changed(self) -> bool:
        before = self.get_doc_before_save()
        if not before:
            return False
        return self.status_rows(before) != self.status_rows(self)

    @staticmethod
    def status_rows(doc) -> list[tuple]:
        return sorted((r.company or "", r.status, r.category) for r in doc.status_map)

    def unit_names(self) -> list[str]:
        return frappe.qb.get_query(
            "HD CRM Org Unit", fields=["name"], filters={"source": self.name}
        ).run(pluck=True)

    def validate_unused(self, units: list[str]):
        from helpdesk.helpdesk.doctype.hd_crm_dashboard.hd_crm_dashboard import (
            HDCRMDashboard,
        )

        HDCRMDashboard.refuse_if_covering(units, _("A unit of {0}").format(self.name))

    def delete_copies(self):
        frappe.db.delete("HD CRM Org Unit", {"source": self.name})
        frappe.db.delete("HD CRM Report Lead", {"source": self.name})

    # ---------- used by the sync and the report ----------

    def client(self) -> CRMClient:
        if self.use_crm_connection:
            return CRMClient.from_settings()
        secret = self.get_password("api_secret", raise_exception=False)
        if not (self.site_url and self.api_key and secret):
            raise CRMError(
                _("Add the site URL, API key and API secret of {0} first.").format(
                    self.name
                )
            )
        return CRMClient(self.site_url, self.api_key, secret)

    def field_map(self) -> dict[str, str]:
        """{fieldname on this doctype: the source's lead field} for the mapped ones."""
        return {t: self.get(t) for t in mapped_fields() if self.get(t)}

    def fields_to_read(self) -> list[str]:
        return sorted({"name", "modified", *self.field_map().values()})

    def categories(self) -> dict[tuple[str, str], str]:
        """{(company, status): category}; company "" is every company of the source."""
        return {(r.company or "", r.status): r.category for r in self.status_map}

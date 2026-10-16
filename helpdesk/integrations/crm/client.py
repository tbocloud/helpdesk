"""A small REST client for the TBO CRM site, using the key and secret in HD CRM Settings."""

import json
from urllib.parse import quote

import frappe
import requests
from frappe import _

TIMEOUT = 20


class CRMError(Exception):
    """The CRM site is unreachable, refused the key, or rejected a request.

    `status` is the HTTP status (None when the site couldn't be reached) and `detail`
    the site's own error message, so callers can tell the cases apart."""

    def __init__(self, message: str, status: int | None = None, detail: str = ""):
        super().__init__(message)
        self.status = status
        self.detail = detail


class CRMPermissionError(CRMError):
    """The CRM site's API user may not read or change this (HTTP 403)."""


# the ERPNext roles that give a user sales (CRM) access on the CRM site
SALES_ROLES = ("Sales User", "Sales Manager")


class CRMClient:
    def __init__(self, site_url: str, api_key: str, api_secret: str):
        self.base = site_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"token {api_key}:{api_secret}",
                "Accept": "application/json",
            }
        )

    @classmethod
    def from_settings(cls, settings=None) -> "CRMClient":
        """From the saved settings, or from `settings` while it is being saved: a newly
        typed secret is still plain text there, and get_password reads it or the stored one."""
        settings = settings or frappe.get_single("HD CRM Settings")
        secret = settings.get_password("api_secret", raise_exception=False)
        if not (settings.site_url and settings.api_key and secret):
            raise CRMError(_("Add the CRM site URL, API key and API secret first."))
        return cls(settings.site_url, settings.api_key, secret)

    def send(self, method: str, path: str, **kwargs):
        try:
            return self.session.request(
                method, f"{self.base}{path}", timeout=TIMEOUT, **kwargs
            )
        except requests.RequestException as e:
            raise CRMError(_("Couldn't reach the CRM site: {0}").format(str(e))) from e

    def request(self, method: str, path: str, **kwargs):
        """The JSON answer, or None when the record doesn't exist (404)."""
        response = self.send(method, path, **kwargs)
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            error = CRMPermissionError if response.status_code == 403 else CRMError
            raise error(
                _("The CRM site refused the API key ({0}).").format(
                    response.status_code
                ),
                response.status_code,
                error_text(response),
            )
        if not response.ok:
            detail = error_text(response)
            raise CRMError(
                _("The CRM site answered {0}: {1}").format(
                    response.status_code, detail
                ),
                response.status_code,
                detail,
            )
        return response.json() if response.content else {}

    def call(self, method: str, post: bool = False, **params):
        """A whitelisted method on the CRM site; returns its `message`. Unlike
        `request`, a 404 raises too: for a method it means the record wasn't found
        or the method isn't there."""
        path = f"/api/method/{method}"
        response = (
            self.send("POST", path, json=params)
            if post
            else self.send("GET", path, params=params)
        )
        if not response.ok:
            detail = error_text(response)
            raise CRMError(
                _("The CRM site answered {0}: {1}").format(
                    response.status_code, detail
                ),
                response.status_code,
                detail,
            )
        return (response.json() if response.content else {}).get("message")

    def logged_user(self) -> str:
        """Who the key belongs to on the CRM site; proves the connection works."""
        data = self.request("GET", "/api/method/frappe.auth.get_logged_user") or {}
        return data.get("message") or ""

    def get_user(self, email: str) -> dict | None:
        data = self.request("GET", f"/api/resource/User/{quote(email)}")
        return (data or {}).get("data")

    def create_user(self, email: str, full_name: str, send_welcome_email: bool) -> dict:
        first, _sep, last = (full_name or email.split("@")[0]).partition(" ")
        data = self.request(
            "POST",
            "/api/resource/User",
            json={
                "email": email,
                "first_name": first,
                "last_name": last or None,
                "enabled": 1,
                "user_type": "System User",
                "send_welcome_email": 1 if send_welcome_email else 0,
            },
        )
        return (data or {}).get("data") or {}

    def enable_user(self, email: str):
        self.request("PUT", f"/api/resource/User/{quote(email)}", json={"enabled": 1})

    def disable_user(self, email: str):
        self.request("PUT", f"/api/resource/User/{quote(email)}", json={"enabled": 0})

    def crm_users(self) -> list[dict]:
        """Enabled desk users with an ERPNext sales role (Sales User or Sales Manager)
        on the CRM site. Read from User itself, so it works with or without Frappe CRM
        installed there."""
        rows = self.get_list(
            "User",
            ["name", "full_name", "first_name", "last_name"],
            [
                ["Has Role", "role", "in", list(SALES_ROLES)],
                ["enabled", "=", 1],
                ["user_type", "=", "System User"],
            ],
        )
        # a user with both roles comes back twice
        users = {}
        for u in rows:
            if u.get("name") and u["name"] != "Administrator":
                users[u["name"]] = {
                    "email": u["name"],
                    "full_name": u.get("full_name")
                    or " ".join(
                        n for n in (u.get("first_name"), u.get("last_name")) if n
                    ),
                }
        return list(users.values())

    def has_doctype(self, doctype: str) -> bool:
        """Whether the CRM site has `doctype`, e.g. CRM Organization only while Frappe
        CRM is installed there."""
        return self.get_doc("DocType", doctype) is not None

    def organizations(self) -> list[dict]:
        data = self.request(
            "GET",
            f"/api/resource/{quote('CRM Organization')}",
            params={
                "fields": json.dumps(["name", "organization_name", "website"]),
                "limit_page_length": 0,
            },
        )
        return (data or {}).get("data") or []

    def erp_customers(self, strict: bool = False) -> list[dict]:
        """ERPNext Customers on the CRM site, shaped like organizations; none without
        ERPNext. With `strict`, a failed read raises instead: when they are the only
        customers there, an empty list would wrongly say every customer is missing."""
        try:
            customers = self.customers()
        except CRMError:
            if strict:
                raise
            # no ERPNext on the CRM site (or no access to it): nothing to add
            return []
        return [
            {
                "name": c.get("name"),
                "organization_name": c.get("customer_name") or c.get("name"),
                "website": c.get("website"),
            }
            for c in customers
        ]

    def customers(self) -> list[dict]:
        """Enabled ERPNext Customers; raises CRMError when the site can't list them."""
        return self.get_list(
            "Customer",
            ["name", "customer_name", "website"],
            [["disabled", "=", 0]],
        )

    def customer_account_managers(self) -> list[dict]:
        """Enabled ERPNext Customers that have an Account Manager (a user on the CRM
        site); raises CRMError when the site can't list them (no ERPNext there)."""
        return self.get_list(
            "Customer",
            ["name", "customer_name", "account_manager"],
            [["disabled", "=", 0], ["account_manager", "is", "set"]],
        )

    def create_organization(self, name: str, website: str | None = None) -> dict:
        data = self.request(
            "POST",
            f"/api/resource/{quote('CRM Organization')}",
            json={"organization_name": name, "website": website or None},
        )
        return (data or {}).get("data") or {}

    def add_role(self, email: str, role: str):
        """Give an existing user an ERPNext sales role on the CRM site. Added as one
        Has Role row through frappe.client.insert, which appends it to the User and
        saves it, so the user's other roles stay."""
        self.request(
            "POST",
            "/api/method/frappe.client.insert",
            json={
                "doc": {
                    "doctype": "Has Role",
                    "parenttype": "User",
                    "parent": email,
                    "parentfield": "roles",
                    "role": role,
                }
            },
        )

    # --- ERPNext on the CRM site, for invoicing (docs/timesheet-invoicing.md) ---

    def get_list(self, doctype: str, fields: list[str], filters=None) -> list[dict]:
        data = self.request(
            "GET",
            f"/api/resource/{quote(doctype)}",
            params={
                "fields": json.dumps(fields),
                "filters": json.dumps(filters or []),
                "limit_page_length": 0,
            },
        )
        return (data or {}).get("data") or []

    def get_doc(self, doctype: str, name: str) -> dict | None:
        """The document, or None when it doesn't exist (404)."""
        data = self.request("GET", f"/api/resource/{quote(doctype)}/{quote(name)}")
        return None if data is None else data.get("data")

    def companies(self) -> list[dict]:
        return self.get_list("Company", ["name", "default_currency"])

    def service_items(self) -> list[dict]:
        """Enabled sales items that aren't stocked: what support hours are billed as."""
        return self.get_list(
            "Item",
            ["name", "item_name"],
            [
                ["disabled", "=", 0],
                ["is_sales_item", "=", 1],
                ["is_stock_item", "=", 0],
            ],
        )

    def taxes_templates(self, company: str) -> list[dict]:
        return self.get_list(
            "Sales Taxes and Charges Template",
            ["name", "title"],
            [["company", "=", company], ["disabled", "=", 0]],
        )

    def income_accounts(self, company: str) -> list[dict]:
        return self.get_list(
            "Account",
            ["name", "account_name"],
            [
                ["company", "=", company],
                ["root_type", "=", "Income"],
                ["is_group", "=", 0],
                ["disabled", "=", 0],
            ],
        )

    def cost_centers(self, company: str) -> list[dict]:
        return self.get_list(
            "Cost Center",
            ["name", "cost_center_name"],
            [["company", "=", company], ["is_group", "=", 0], ["disabled", "=", 0]],
        )

    def template_taxes(self, template: str) -> list[dict]:
        """The tax rows of a Sales Taxes and Charges Template, ready for an invoice."""
        data = self.request(
            "GET",
            "/api/method/erpnext.controllers.accounts_controller.get_taxes_and_charges",
            params={
                "master_doctype": "Sales Taxes and Charges Template",
                "master_name": template,
            },
        )
        return (data or {}).get("message") or []

    def create_sales_invoice(self, invoice: dict) -> dict:
        """Insert a draft Sales Invoice; it is never submitted from the hub."""
        data = self.request(
            "POST",
            f"/api/resource/{quote('Sales Invoice')}",
            json={**invoice, "docstatus": 0},
        )
        created = (data or {}).get("data") or {}
        if not created.get("name"):
            raise CRMError(_("The CRM site didn't return the new invoice."))
        return created

    def delete_sales_invoice(self, name: str):
        self.request("DELETE", f"/api/resource/{quote('Sales Invoice')}/{quote(name)}")

    def sales_invoices(self, names: list[str]) -> list[dict]:
        return self.get_list(
            "Sales Invoice",
            ["name", "docstatus", "status", "grand_total", "outstanding_amount"],
            [["name", "in", names]],
        )

    # --- ERPNext on the CRM site, for holidays and leave (read only) ---

    def holiday_lists(self) -> list[dict]:
        return self.get_list("Holiday List", ["name", "from_date", "to_date"])

    def company_holiday_lists(self) -> list[dict]:
        """Each company with its default holiday list."""
        return self.get_list("Company", ["name", "default_holiday_list"])

    def holidays(self, holiday_list: str) -> list[dict]:
        """The rows of a Holiday List: holiday_date, description, weekly_off."""
        doc = self.get_doc("Holiday List", holiday_list)
        if doc is None:
            raise CRMError(
                _("There's no holiday list {0} on the CRM site.").format(holiday_list)
            )
        return doc.get("holidays") or []

    def approved_leave(self, start, end) -> list[dict]:
        """Approved, submitted Leave Applications overlapping `start` to `end`."""
        return self.get_list(
            "Leave Application",
            [
                "name",
                "employee",
                "employee_name",
                "from_date",
                "to_date",
                "half_day",
                "half_day_date",
                "leave_type",
            ],
            [
                ["status", "=", "Approved"],
                ["docstatus", "=", 1],
                ["to_date", ">=", str(start)],
                ["from_date", "<=", str(end)],
            ],
        )

    def employees(self, names: list[str]) -> list[dict]:
        return self.get_list(
            "Employee",
            ["name", "user_id", "company_email", "prefered_email"],
            [["name", "in", names]],
        )


def error_text(response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200]
    messages = body.get("_server_messages")
    if messages:
        try:
            first = json.loads(json.loads(messages)[0])
            return frappe.utils.strip_html(first.get("message", ""))[:200]
        except (ValueError, TypeError, IndexError, AttributeError):
            pass
    return str(body.get("exception") or body.get("message") or "")[:200]

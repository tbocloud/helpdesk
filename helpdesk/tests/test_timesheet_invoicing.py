from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, get_first_day, get_last_day, nowdate

from helpdesk.api import crm as crm_api
from helpdesk.api import invoices as api
from helpdesk.integrations.crm.invoices import CustomerNotInERPNext
from helpdesk.test_utils import (
    FAKE_COMPANY,
    FAKE_ITEM,
    FAKE_TAXES,
    FakeCRM,
    create_customer,
    enable_invoicing,
    get_billed_invoices,
    hold_commits,
    make_customer_project,
    make_support_contract,
    make_task,
    make_tasky_user,
    make_timesheet,
    run_as_user,
)

FROM_SETTINGS = "helpdesk.integrations.crm.client.CRMClient.from_settings"
CUSTOMER = "Invoice Traders LLC"
NO_CONTRACT_CUSTOMER = "Pay As You Go Ltd"
PROJECT_MANAGER = ("pm@invoicing.example", "Priya Menon")
AGENT = ("agent@invoicing.example", "Arun Das")


class TestTimesheetInvoicing(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        self.addCleanup(frappe.set_user, "Administrator")
        frappe.set_user("Administrator")
        create_customer(CUSTOMER)
        create_customer(NO_CONTRACT_CUSTOMER)
        self.project = make_customer_project(CUSTOMER, "Invoice Traders ERP")
        self.other_project = make_customer_project(
            NO_CONTRACT_CUSTOMER, "Pay As You Go Website"
        )
        enable_invoicing()
        # last month is one period of a monthly contract that started two months before
        self.start = get_first_day(add_months(nowdate(), -1))
        self.end = get_last_day(self.start)
        self.contract = make_support_contract(
            CUSTOMER,
            add_months(self.start, -2),
            add_days(add_months(self.start, 10), -1),
            hours_per_period=10,
            rate_per_extra_hour=1500,
            currency="INR",
        )
        self.logs = [
            self.log(self.project, 6, 1),
            self.log(self.project, 7, 9),
        ]
        self.crm = FakeCRM(erp_customers=[CUSTOMER, NO_CONTRACT_CUSTOMER])
        crm = patch(FROM_SETTINGS, return_value=self.crm)
        crm.start()
        self.addCleanup(crm.stop)

    def log(self, project, hours, day, billable=1) -> str:
        sheet = make_timesheet(
            project,
            hours,
            f"{add_days(self.start, day)} 10:00:00",
            billable=billable,
        )
        return sheet.time_logs[0].name

    def preview(self, customer=CUSTOMER, mode="extra", **kwargs):
        return api.get_invoice_preview(
            customer, str(self.start), str(self.end), mode, **kwargs
        )

    def create(self, customer=CUSTOMER, mode="extra", **kwargs):
        return api.create_invoice_draft(
            customer, str(self.start), str(self.end), mode, **kwargs
        )

    # --- preview ---

    def test_extra_hours_bills_only_beyond_the_contract(self):
        preview = self.preview()

        self.assertEqual(preview["mode"], "extra")
        self.assertEqual(preview["contract"]["name"], self.contract.name)
        self.assertEqual(preview["hours_logged"], 13)
        self.assertEqual(preview["hours_covered"], 10)
        self.assertEqual(preview["hours_billed"], 3)
        # the contract's rate per extra hour, not the default 1000
        self.assertEqual((preview["rate"], preview["rate_from"]), (1500, "contract"))
        self.assertEqual(preview["amount"], 4500)
        (line,) = preview["lines"]
        self.assertEqual(line["project"], self.project)
        self.assertEqual(line["label"], "Invoice Traders ERP")

    def test_all_hours_bills_everything_at_the_contract_rate(self):
        preview = self.preview(mode="all")

        self.assertEqual(preview["mode"], "all")
        self.assertEqual(preview["hours_covered"], 0)
        self.assertEqual(preview["hours_billed"], 13)
        self.assertEqual(preview["amount"], 19500)

    def test_default_rate_without_a_contract_rate(self):
        frappe.db.set_value(
            "HD Support Contract", self.contract.name, "rate_per_extra_hour", 0
        )
        preview = self.preview()
        self.assertEqual((preview["rate"], preview["rate_from"]), (1000, "default"))
        self.assertEqual(preview["amount"], 3000)

    def test_customer_without_contract_bills_all_hours_at_default_rate(self):
        self.log(self.other_project, 2.5, 3)
        preview = self.preview(NO_CONTRACT_CUSTOMER)

        self.assertIsNone(preview["contract"])
        self.assertEqual(preview["mode"], "all")
        self.assertEqual(preview["hours_billed"], 2.5)
        self.assertEqual(preview["amount"], 2500)

    def test_extra_hours_needs_a_contract_period(self):
        with self.assertRaises(frappe.ValidationError):
            api.get_invoice_preview(
                CUSTOMER, str(self.start), str(add_days(self.end, -5)), "extra"
            )

    def test_non_billable_time_is_left_out(self):
        self.log(self.project, 4, 2, billable=0)
        self.assertEqual(self.preview()["hours_logged"], 13)

    def test_lines_by_task(self):
        task = make_task(self.project, "Payroll fixes").name
        make_timesheet(
            self.project, 5, f"{add_days(self.start, 12)} 10:00:00", task=task
        )
        preview = self.preview(mode="all", by_task=True)
        labels = {line["label"]: line["hours"] for line in preview["lines"]}
        self.assertEqual(labels["Invoice Traders ERP · Payroll fixes"], 5)
        self.assertEqual(labels["Invoice Traders ERP"], 13)
        # by project only, the task's time joins its project's line
        (line,) = self.preview(mode="all")["lines"]
        self.assertEqual(line["hours"], 18)

    # --- create ---

    def test_create_makes_a_draft_and_marks_the_time_logs(self):
        result = self.create(expected_hours=3)

        invoice = self.crm.invoices[result["invoice"]]
        self.assertEqual(invoice["docstatus"], 0)
        self.assertEqual(invoice["customer"], CUSTOMER)
        self.assertEqual(invoice["company"], FAKE_COMPANY)
        self.assertEqual(invoice["posting_date"], nowdate())
        (item,) = invoice["items"]
        self.assertEqual(
            (item["item_code"], item["qty"], item["rate"]), (FAKE_ITEM, 3, 1500)
        )
        self.assertNotIn("taxes_and_charges", invoice)

        record = frappe.get_doc("HD Customer Invoice", result["name"])
        self.assertEqual(record.status, "Linked")
        self.assertEqual(record.hours_covered, 10)
        self.assertEqual(record.amount, 4500)
        self.assertTrue(
            record.invoice_url.endswith(f"/app/sales-invoice/{result['invoice']}")
        )
        # every log of the period is settled, the covered ones too
        self.assertEqual(set(get_billed_invoices(self.logs).values()), {record.name})

    def test_taxes_template_from_settings(self):
        enable_invoicing(invoice_taxes_template=FAKE_TAXES)
        invoice = self.crm.invoices[self.create()["invoice"]]
        self.assertEqual(invoice["taxes_and_charges"], FAKE_TAXES)
        self.assertEqual(invoice["taxes"][0]["rate"], 18)

    def test_customer_missing_in_erpnext_stops_before_anything(self):
        self.crm.erp = [NO_CONTRACT_CUSTOMER]
        with self.assertRaises(CustomerNotInERPNext):
            self.create()
        self.assertFalse(self.crm.invoices)
        self.assertFalse(any(get_billed_invoices(self.logs).values()))

    def test_failed_remote_create_marks_nothing(self):
        self.crm.fail_invoices = True
        with self.assertRaises(frappe.ValidationError):
            self.create()
        self.assertFalse(any(get_billed_invoices(self.logs).values()))
        self.assertFalse(
            frappe.db.exists("HD Customer Invoice", {"customer": CUSTOMER})
        )

    def test_changed_hours_since_preview_stops(self):
        with self.assertRaises(frappe.ValidationError):
            self.create(expected_hours=2)
        self.assertFalse(self.crm.invoices)

    def test_no_double_billing(self):
        self.create()
        self.assertEqual(self.preview()["hours_logged"], 0)
        with self.assertRaises(frappe.ValidationError):
            self.create()
        self.assertEqual(len(self.crm.invoices), 1)

        # time logged later in the same period: the included hours are used up
        late = self.log(self.project, 2, 20)
        preview = self.preview()
        self.assertEqual((preview["hours_covered"], preview["hours_billed"]), (0, 2))
        self.create()
        self.assertTrue(get_billed_invoices([late])[late])

    # --- unlink and list ---

    def test_unlink_only_once_the_invoice_is_gone(self):
        result = self.create()
        with self.assertRaises(frappe.ValidationError):
            api.unlink_invoice(result["name"])

        self.crm.invoices.pop(result["invoice"])  # deleted in ERPNext: 404
        self.assertEqual(api.unlink_invoice(result["name"])["status"], "Unlinked")
        self.assertFalse(any(get_billed_invoices(self.logs).values()))
        # the period can be billed again, with its included hours back
        self.assertEqual(self.preview()["hours_billed"], 3)

    def test_unlink_a_cancelled_invoice(self):
        result = self.create()
        self.crm.invoices[result["invoice"]]["docstatus"] = 2
        self.assertEqual(api.unlink_invoice(result["name"])["status"], "Unlinked")

    def test_list_and_statuses(self):
        result = self.create()
        rows = api.get_invoices(CUSTOMER)["rows"]
        self.assertEqual([r["name"] for r in rows], [result["name"]])
        self.assertEqual(api.get_invoices(NO_CONTRACT_CUSTOMER)["rows"], [])

        frappe.cache.delete_value(f"hd_customer_invoice_status:{result['invoice']}")
        self.assertEqual(
            api.get_invoice_statuses([result["name"]]), {result["name"]: "Draft"}
        )

    # --- permissions ---

    def test_only_managers_bill(self):
        make_tasky_user(*PROJECT_MANAGER, roles=("Project Manager",))
        make_tasky_user(*AGENT)
        for user in (PROJECT_MANAGER[0], AGENT[0]):
            for call in (
                self.preview,
                self.create,
                lambda: api.get_invoices(CUSTOMER),
                lambda: api.unlink_invoice("BILL-00001"),
            ):
                with self.assertRaises(frappe.PermissionError):
                    run_as_user(user, call)
            with self.assertRaises(frappe.PermissionError):
                run_as_user(user, crm_api.get_invoicing_options)
        self.assertFalse(self.crm.invoices)


class TestInvoicingSettings(FrappeTestCase):
    def setUp(self):
        hold_commits(self)
        # the sync switch needs the API secret; invoicing is checked either way
        enable_invoicing(enabled=0)
        self.crm = FakeCRM()

    def save(self, **values):
        settings = frappe.get_single("HD CRM Settings")
        settings.update(values)
        with patch(FROM_SETTINGS, return_value=self.crm):
            settings.save(ignore_permissions=True)

    def test_valid_settings_save(self):
        self.save(
            invoice_company=FAKE_COMPANY,
            invoice_item=FAKE_ITEM,
            invoice_taxes_template=FAKE_TAXES,
            invoice_cost_center="Main - TBO",
            invoice_hourly_rate=1200,
        )
        self.assertEqual(
            frappe.db.get_single_value("HD CRM Settings", "invoice_hourly_rate"), 1200
        )

    def test_unknown_records_are_refused(self):
        for values in (
            {"invoice_company": "Nobody Ltd"},
            {"invoice_item": "Laptop"},
            {"invoice_taxes_template": "VAT 5%"},
            {"invoice_income_account": "Sales - XYZ"},
        ):
            with self.assertRaises(frappe.ValidationError, msg=values):
                self.save(**values)

    def test_rate_and_item_are_required(self):
        with self.assertRaises(frappe.ValidationError):
            self.save(invoice_hourly_rate=0)
        with self.assertRaises(frappe.ValidationError):
            self.save(invoice_item="")

    def test_clearing_the_company_turns_invoicing_off(self):
        enable_invoicing(enabled=0, invoice_taxes_template=FAKE_TAXES)
        settings = frappe.get_single("HD CRM Settings")
        settings.invoice_company = ""
        # no company: nothing to check on the CRM site
        with patch(FROM_SETTINGS, side_effect=AssertionError("CRM called")):
            settings.save(ignore_permissions=True)
        saved = frappe.get_single("HD CRM Settings")
        for field in (
            "invoice_company",
            "invoice_item",
            "invoice_taxes_template",
            "invoice_income_account",
            "invoice_cost_center",
        ):
            self.assertFalse(saved.get(field), field)

    def test_other_changes_dont_call_the_crm(self):
        settings = frappe.get_single("HD CRM Settings")
        settings.crm_role = "Sales Manager"
        with patch(FROM_SETTINGS, side_effect=AssertionError("CRM called")):
            settings.save(ignore_permissions=True)

    def test_options_come_from_the_crm(self):
        with patch(FROM_SETTINGS, return_value=self.crm):
            options = crm_api.get_invoicing_options(FAKE_COMPANY)
        self.assertTrue(options["ok"])
        self.assertEqual(options["companies"][0]["name"], FAKE_COMPANY)
        self.assertEqual(options["taxes_templates"][0]["name"], FAKE_TAXES)

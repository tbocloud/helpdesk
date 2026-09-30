# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime

KEEP_DAYS = 30


class HDGitHubDelivery(Document):
    pass


def clear_old_deliveries():
    """Daily: the log only needs to cover redeliveries and recent debugging."""
    delivery = frappe.qb.DocType("HD GitHub Delivery")
    frappe.qb.from_(delivery).delete().where(
        delivery.creation < add_days(now_datetime(), -KEEP_DAYS)
    ).run()

# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_days, now_datetime

KEEP_DAYS = 30


class HDChatwootEvent(Document):
    pass


def clear_old_events():
    """Daily: the log only needs to cover Chatwoot's retries and recent debugging."""
    event = frappe.qb.DocType("HD Chatwoot Event")
    frappe.qb.from_(event).delete().where(
        event.creation < add_days(now_datetime(), -KEEP_DAYS)
    ).run()

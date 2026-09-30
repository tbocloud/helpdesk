from helpdesk.tasky.setup import backfill_hd_customer, setup_erpnext_projects


def execute():
    setup_erpnext_projects()
    backfill_hd_customer()

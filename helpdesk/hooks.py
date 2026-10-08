app_name = "helpdesk"
app_title = "TBO Support"
app_publisher = "Frappe Technologies"
app_description = "Customer Service Software"
app_icon = "octicon octicon-file-directory"
app_color = "grey"
app_email = "hello@frappe.io"
app_license = "AGPLv3"
require_type_annotated_api_methods = True

add_to_apps_screen = [
    {
        "name": "helpdesk",
        "logo": "/assets/helpdesk/desk/favicon.svg",
        "title": "TBO Support",
        "route": "/helpdesk",
        "has_permission": "helpdesk.api.permission.has_app_permission",
    }
]

get_site_info = "helpdesk.activation.get_site_info"

before_install = "helpdesk.install.before_install"
after_install = "helpdesk.setup.install.after_install"

# only System Managers use the Frappe desk; everyone else is sent to /helpdesk
update_website_context = ["helpdesk.desk_access.redirect_desk_to_helpdesk"]
after_migrate = [
    "helpdesk.search.build_index_in_background",
    "helpdesk.search.download_corpus",
    "helpdesk.setup.after_migrate",
]

# Full Text Search
# ------------------

sqlite_search = ["helpdesk.search_sqlite.HelpdeskSearch"]

scheduler_events = {
    "all": [
        "helpdesk.search.build_index_if_not_exists",
        "helpdesk.search.download_corpus",
    ],
    "cron": {
        # every minute: new customer tickets arrive quickly (sites also ping on raise)
        "* * * * *": [
            "helpdesk.tasks.pull_client_tickets",
        ],
        # every 15 minutes: SLA reminders, so a short first-reply SLA isn't missed
        "*/15 * * * *": [
            "helpdesk.work_reminders.send_ticket_reminders",
            "helpdesk.helpdesk.doctype.hd_meeting.hd_meeting.sync_with_outlook",
        ],
        "*/5 * * * *": [
            "helpdesk.tasks.push_ticket_statuses",
            "helpdesk.tasks.sync_conversations",
            "helpdesk.content_sync.sync_content_approvals",
            "helpdesk.helpdesk.doctype.hd_meeting.hd_meeting.send_reminders",
            "helpdesk.copilot.runs.expire_stale_leases",
        ],
        # every 10 minutes: new hub errors to the team's chat channel
        "*/10 * * * *": [
            "helpdesk.error_alerts.post_error_digest",
        ],
        # 10:00 every day: each assignee's morning brief
        "0 10 * * *": [
            "helpdesk.morning_brief.send_morning_briefs",
        ],
        # 09:00: from the planning day on, next month's content plans
        "0 9 * * *": [
            "helpdesk.helpdesk.doctype.hd_content_package.hd_content_package.plan_upcoming_months",
        ],
        # 11:00: remind clients about posts waiting for approval, then alert the team
        "0 11 * * *": [
            "helpdesk.content_follow_up.send_client_follow_ups",
        ],
        # Monday 08:00: last week's summary per customer
        "0 8 * * 1": [
            "helpdesk.work_summary.send_weekly_summaries",
        ],
    },
    "daily": [
        "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.close_tickets_after_n_days",
        "helpdesk.tasks.health_check_connections",
        "helpdesk.tasks.retry_pending_triages",
        "helpdesk.helpdesk.doctype.hd_content_post.hd_content_post.send_due_reminders",
        "helpdesk.work_reminders.send_task_reminders",
        "helpdesk.work_reminders.send_hold_reminders",
        "helpdesk.work_calendar.sync_saturdays_off",
        "helpdesk.helpdesk.doctype.hd_github_delivery.hd_github_delivery.clear_old_deliveries",
        "helpdesk.helpdesk.doctype.hd_chatwoot_event.hd_chatwoot_event.clear_old_events",
        "helpdesk.support_contracts.send_support_hours_alerts",
    ],
    "hourly": [
        "helpdesk.triage.fail_stuck_triages",
        "helpdesk.integrations.crm.users.sync_users_job",
        "helpdesk.helpdesk.doctype.hd_content_post.hd_content_post.send_missed_post_alerts",
    ],
    "hourly_long": [
        "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.update_sla_status_in_ticket"
    ],
    "weekly": [
        "helpdesk.tasks.sync_model_pricing",
    ],
}


website_route_rules = [
    {
        "from_route": "/helpdesk/<path:app_path>",
        "to_route": "helpdesk",
    },
]

user_invitation = {
    "allowed_roles": {
        "Agent Manager": [
            "Agent",
            "Agent Manager",
            "HD Customer",
            "HD Customer Manager",
        ],
        "System Manager": [
            "Agent",
            "Agent Manager",
            "System Manager",
            "HD Customer",
            "HD Customer Manager",
        ],
    },
    "after_accept": "helpdesk.helpdesk.hooks.user_invitation.after_accept",
    "extra_invite_params": ["customer", "contact"],
}

doc_events = {
    "File": {
        "after_insert": "helpdesk.storage.s3.after_insert",
    },
    # a new or re-activated agent gets their TBO CRM user (helpdesk/integrations/crm)
    "HD Agent": {
        "after_insert": "helpdesk.integrations.crm.users.on_agent_change",
        "on_update": "helpdesk.integrations.crm.users.on_agent_change",
    },
    "Assignment Rule": {
        "on_trash": "helpdesk.extends.assignment_rule.on_assignment_rule_trash",
        "validate": "helpdesk.extends.assignment_rule.on_assignment_rule_validate",
    },
    "Customer": {
        "after_insert": "helpdesk.integrations.erpnext.customer.after_insert",
        "on_update": "helpdesk.integrations.erpnext.customer.on_update",
        "before_rename": "helpdesk.integrations.erpnext.customer.before_rename",
        "after_rename": "helpdesk.integrations.erpnext.customer.after_rename",
        "on_trash": "helpdesk.integrations.erpnext.customer.on_trash",
    },
    "User Permission": {
        "before_validate": "helpdesk.integrations.erpnext.user_permission.before_validate",
        "after_insert": "helpdesk.integrations.erpnext.user_permission.after_insert",
        "on_update": "helpdesk.integrations.erpnext.user_permission.on_update",
        "on_trash": "helpdesk.integrations.erpnext.user_permission.on_trash",
    },
    "DocShare": {
        "before_validate": "helpdesk.integrations.erpnext.doc_share.before_validate",
        "after_insert": "helpdesk.integrations.erpnext.doc_share.after_insert",
        "on_update": "helpdesk.integrations.erpnext.doc_share.on_update",
        "on_trash": "helpdesk.integrations.erpnext.doc_share.on_trash",
    },
    "Notification Log": {
        "before_insert": "helpdesk.extends.notification_log.before_insert",
    },
    "HD Ticket": {
        "after_insert": [
            "helpdesk.triage.auto_triage_ticket",
            "helpdesk.copilot.runs.on_ticket_insert",
        ],
        "on_update": [
            "helpdesk.chatwoot_bridge.on_ticket_update",
            "helpdesk.kb_drafts.on_ticket_update",
        ],
    },
    "Communication": {
        "after_insert": "helpdesk.chatwoot_bridge.on_communication_insert",
    },
}

# For List View
permission_query_conditions = {
    "HD Ticket": "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.permission_query",
    "HD Saved Reply": "helpdesk.helpdesk.doctype.hd_saved_reply.hd_saved_reply.permission_query",
    "HD Customer": "helpdesk.helpdesk.doctype.hd_customer.hd_customer.permission_query",
    "Project": "helpdesk.tasky.permissions.project_query",
    "Task": "helpdesk.tasky.permissions.task_query",
    "Timesheet": "helpdesk.tasky.permissions.timesheet_query",
    "HD Pull Request": "helpdesk.tasky.permissions.pull_request_query",
    "HD Content Post": "helpdesk.helpdesk.doctype.hd_content_post.hd_content_post.permission_query",
    "HD Content Campaign": "helpdesk.helpdesk.doctype.hd_content_campaign.hd_content_campaign.permission_query",
    "HD Work Summary": "helpdesk.helpdesk.doctype.hd_work_summary.hd_work_summary.permission_query",
}

has_permission = {
    "HD Ticket": "helpdesk.helpdesk.doctype.hd_ticket.hd_ticket.has_permission",
    "HD Saved Reply": "helpdesk.helpdesk.doctype.hd_saved_reply.hd_saved_reply.has_permission",
    "HD Customer": "helpdesk.helpdesk.doctype.hd_customer.hd_customer.has_permission",
    "Project": "helpdesk.tasky.permissions.project_has_permission",
    "Task": "helpdesk.tasky.permissions.task_has_permission",
    "Timesheet": "helpdesk.tasky.permissions.timesheet_has_permission",
    "HD Pull Request": "helpdesk.tasky.permissions.pull_request_has_permission",
    "HD Content Post": "helpdesk.helpdesk.doctype.hd_content_post.hd_content_post.has_permission",
    "HD Content Campaign": "helpdesk.helpdesk.doctype.hd_content_campaign.hd_content_campaign.has_permission",
    "HD Work Summary": "helpdesk.helpdesk.doctype.hd_work_summary.hd_work_summary.has_permission",
}


# DocType Class
# ---------------
# Override standard doctype classes
override_doctype_class = {  # Frappe v15 has no extend_doctype_class; only helpdesk overrides File here - nosemgrep
    "Email Account": "helpdesk.overrides.email_account.CustomEmailAccount",
    "Assignment Rule": "helpdesk.overrides.assignment_rule.HelpdeskAssignmentRule",
    "User Invitation": "helpdesk.overrides.user_invitation.HelpdeskUserInvitation",
    "File": "helpdesk.overrides.file.HelpdeskFile",
}

ignore_links_on_delete = [
    "HD Notification",
    # a meeting stays in Outlook after its ticket is deleted
    "HD Meeting",
    "HD Ticket Comment",
    # AI cost records are an audit trail; they keep the old ticket number
    "HDS AI Usage Log",
    # deleting a project deletes its files, and each File takes its HD Project File along
    "HD Project File",
]

# setup wizard
# setup_wizard_requires = "assets/helpdesk/js/setup_wizard.js"
# setup_wizard_stages = "helpdesk.setup.setup_wizard.get_setup_stages"
setup_wizard_complete = "helpdesk.setup.setup_wizard.setup_complete"


# Testing
# ---------------

before_tests = "helpdesk.test_utils.before_tests"
auth_hooks = ["helpdesk.auth.authenticate"]

default_log_clearing_doctypes = {
    "HDS AI Usage Log": 90,
    "HDS Site Login Log": 180,
    "HDS Remote Audit Log": 365,
    "HDS Copilot Event": 90,
}

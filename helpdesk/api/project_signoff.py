"""Training and UAT sign-offs on a project (Project -> Sign-off tab, and the lead page's
Documents card) and their templates.

Everyone who can read the project sees its sign-offs. Admins, the project's
managers and lead, and a sign-off's trainer create, send, clarify and reopen; the
owner of the lead the project was made for creates and sends from the lead page.
Templates are managed by project managers. Customers never use these endpoints;
they answer on the token page (helpdesk.api.signoff_portal).
See docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Max
from frappe.utils import cint, cstr, get_datetime, get_fullname

from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    EDITABLE_STATUSES,
    NEEDS_FOLLOW_UP,
    SENT,
    SIGNED,
    TRAINING,
    UAT,
    HDProjectSignoff,
)
from helpdesk.tasky.permissions import (
    can_manage_project,
    get_project_team,
    is_project_manager,
)

SIGNOFF = "HD Project Signoff"
# what a reworded question loses
RESET_ANSWER = {
    "response": "Pending",
    "customer_comment": None,
    "responded_on": None,
    "clarification_task": None,
    "clarified_on": None,
    "clarified_by": None,
    "clarification_note": None,
}
TEMPLATE = "HD Signoff Template"


# --- sign-offs ---


@frappe.whitelist()
def get_project_signoffs(project: str) -> dict:
    """The project's sign-offs with progress, the roll-up and the completion letter."""
    project = _check_project(project)
    signoffs = frappe.get_all(
        SIGNOFF,
        filters={"project": project},
        fields=[
            "name",
            "module_title",
            "signoff_type",
            "template",
            "status",
            "training_date",
            "trainer",
            "signatory_name",
            "signatory_email",
            "link_sent_on",
            "signed_on",
            "creation",
        ],
        order_by="creation asc",
        limit_page_length=0,
    )
    counts = _item_counts([s.name for s in signoffs])
    viewed = _viewed_since_sent(signoffs)
    for s in signoffs:
        s.update(counts.get(s.name, {"total": 0, "done": 0, "follow_up": 0}))
        s.trainer_name = get_fullname(s.trainer) if s.trainer else None
        # Sent reads Viewed once the customer opened the link with their code
        s.customer_status = "Viewed" if s.name in viewed else s.status
    letter, plan = frappe.db.get_value(
        "Project", project, ["custom_signoff_letter", "custom_crm_plan"]
    )
    # the completion letter is the training's: a UAT isn't in its roll-up
    training = [s for s in signoffs if s.signoff_type != UAT]
    signed = sum(1 for s in training if s.status == SIGNED)
    return {
        "signoffs": signoffs,
        "signed": signed,
        "total": len(training),
        "completion_letter": (
            _file_info(letter)
            if letter and training and signed == len(training)
            else None
        ),
        "can_create": can_manage_project(project),
        # made from an implementation plan on the ERP site: its SRS gives the UAT's tests
        "can_create_uat": bool(plan) and can_manage_project(project),
    }


@frappe.whitelist()
def get_signoff_form(project: str, lead: str | None = None) -> dict:
    """What the New sign-off dialog offers: active templates, the team (trainers), the
    customer's contacts and who is copied by default (the project lead and you). `lead`: opened
    from that lead's page, by someone who may not read the project but owns the lead."""
    project = _project_for(project, lead)
    info = frappe.db.get_value(
        "Project",
        project,
        ["project_name", "customer", "project_type", "project_lead", "custom_crm_plan"],
        as_dict=True,
    )
    me = frappe.session.user
    return {
        "project_name": info.project_name or project,
        "project_type": info.project_type,
        "customer": info.customer,
        "templates": _active_templates(),
        "team": [
            {"user": u, "full_name": get_fullname(u)} for u in get_project_team(project)
        ],
        "contacts": _customer_contacts(info.customer) if info.customer else [],
        "default_cc": [
            e
            for e in dict.fromkeys((info.project_lead, me))
            if e and e not in ("Administrator", "Guest")
        ],
        # made from an implementation plan on the ERP site: its SRS gives the UAT's tests
        "can_create_uat": bool(info.custom_crm_plan),
        # a placeholder left in the mail is named in the words of the field that fills it
        "placeholder_labels": HDProjectSignoff.placeholder_labels(),
    }


@frappe.whitelist()
def preview_signoff_mail(
    project: str,
    signoff_type: str = TRAINING,
    template: str | None = None,
    signatory_contact: str | None = None,
    module_title: str | None = None,
    training_date: str | None = None,
    trainer: str | None = None,
    lead: str | None = None,
) -> dict:
    """The mail the dialog fills in: the template's (or the standard) subject and body with
    what is known so far, its CC, and the placeholders still `missing` (they hold the mail
    back). Nothing is saved."""
    project = _project_for(project, lead)
    doc = frappe.get_doc(
        {
            "doctype": SIGNOFF,
            "project": project,
            "signoff_type": UAT if signoff_type == UAT else TRAINING,
            "template": template or None,
            "module_title": cstr(module_title).strip(),
            "training_date": training_date or None,
            "trainer": trainer or None,
            "signatory_contact": signatory_contact or None,
        }
    )
    doc.project_name = frappe.db.get_value("Project", project, "project_name")
    doc.customer = frappe.db.get_value("Project", project, "customer")
    if signatory_contact:
        doc.signatory_name = frappe.db.get_value(
            "Contact", signatory_contact, "full_name"
        )
    if doc.is_uat():
        # the modules a UAT covers are its tests' sections
        for case in _uat_cases(project, cached=True).get("cases") or []:
            doc.append("items", {"section": cstr(case.get("module"))})
    return doc.render_mail()


@frappe.whitelist()
def get_signoff(signoff: str) -> dict:
    doc = _get_signoff(signoff)
    can_manage = _can_manage(doc)
    return {
        "name": doc.name,
        "project": doc.project,
        "project_name": doc.project_name,
        "customer": doc.customer,
        "module_title": doc.module_title,
        "signoff_type": doc.signoff_type,
        # a UAT's state on the ERP site; differs from `status` until recorded
        "crm_recorded": doc.crm_recorded,
        "template": doc.template,
        "status": doc.status,
        "customer_status": doc.customer_status(),
        "email_subject": doc.email_subject,
        "email_body": doc.email_body,
        "cc_emails": doc.cc_emails,
        "reminder_sent_on": doc.reminder_sent_on,
        "training_date": doc.training_date,
        "trainer": doc.trainer,
        "trainer_name": get_fullname(doc.trainer) if doc.trainer else None,
        "signatory_contact": doc.signatory_contact,
        "signatory_name": doc.signatory_name,
        "signatory_email": doc.signatory_email,
        "link_open": doc.link_is_open(),
        "link_sent_on": doc.link_sent_on,
        "link_expires_on": doc.link_expires_on if doc.link_token_hash else None,
        "signed_on": doc.signed_on,
        "signer_name": doc.signer_name,
        "signer_designation": doc.signer_designation,
        "signer_email": doc.signer_email,
        "signer_ip": doc.signer_ip,
        "audit_ref": doc.audit_ref,
        "signed_pdf": _file_info(doc.signed_pdf) if doc.signed_pdf else None,
        "counts": doc.counts(),
        "items": [
            {
                "name": row.name,
                "section": row.section,
                "question": row.question,
                "help_text": row.help_text,
                "response": row.response,
                "customer_comment": row.customer_comment,
                "responded_on": row.responded_on,
                "clarification_task": row.clarification_task,
                "clarified_on": row.clarified_on,
                "clarified_by_name": (
                    get_fullname(row.clarified_by) if row.clarified_by else None
                ),
                "clarification_note": row.clarification_note,
            }
            for row in doc.items
        ],
        "log": [
            {
                "event": row.event,
                "item": row.item,
                "detail": row.detail,
                "by_name": row.by_name,
                "at": row.at,
            }
            for row in reversed(doc.log)
        ],
        "can_manage": can_manage,
        "can_edit": can_manage and doc.status in EDITABLE_STATUSES,
    }


@frappe.whitelist(methods=["POST"])
def create_signoff(
    project: str,
    module_title: str,
    signatory_contact: str,
    trainer: str,
    template: str | None = None,
    training_date: str | None = None,
    email_subject: str | None = None,
    email_body: str | None = None,
    cc_emails: str | None = None,
    send: int | str = 0,
    lead: str | None = None,
) -> dict:
    """A training sign-off, saved as a draft, or (`send`) sent to the customer at once with its
    mail; a send that fails saves nothing."""
    project = _project_for(project, lead, manage=True)
    _check_template(template, TRAINING)
    if not cstr(module_title).strip():
        frappe.throw(_("Name the module this sign-off is for, e.g. Accounts."))
    if not cstr(trainer).strip():
        frappe.throw(_("Pick the trainer who ran the training."))
    doc = frappe.get_doc(
        {
            "doctype": SIGNOFF,
            "project": project,
            "template": template or None,
            "module_title": cstr(module_title).strip(),
            "training_date": training_date or None,
            "trainer": cstr(trainer).strip(),
            "signatory_contact": signatory_contact,
            "status": "Draft",
            **_mail_fields(email_subject, email_body, cc_emails),
        }
    ).insert(ignore_permissions=True)
    return _sent_if_asked(doc, send)


@frappe.whitelist(methods=["POST"])
def create_uat_signoff(
    project: str,
    signatory_contact: str,
    trainer: str,
    template: str | None = None,
    email_subject: str | None = None,
    email_body: str | None = None,
    cc_emails: str | None = None,
    send: int | str = 0,
    lead: str | None = None,
) -> dict:
    """A UAT sign-off for a project made from an implementation plan: a test case for
    each functional requirement of the plan's approved SRS on the ERP site (its module the
    section, its steps and expected result the help text). A draft, edited and sent like
    any sign-off, or (`send`) sent at once with its mail."""
    project = _project_for(project, lead, manage=True)
    _check_template(template, UAT)
    plan = frappe.db.get_value("Project", project, "custom_crm_plan")
    if not plan:
        frappe.throw(_("This project wasn't made from an implementation plan."))
    if not cstr(trainer).strip():
        frappe.throw(_("Pick who tests with the client."))
    found = _uat_cases(project)
    cases = found.get("cases") or []
    if not cases:
        frappe.throw(_("The plan's SRS has no requirements to test."))
    doc = frappe.get_doc(
        {
            "doctype": SIGNOFF,
            "project": project,
            "signoff_type": UAT,
            "template": template or None,
            "crm_plan": plan,
            **_mail_fields(email_subject, email_body, cc_emails),
            "module_title": _("User acceptance testing ({0})").format(
                found.get("srs") or plan
            )[:140],
            "trainer": cstr(trainer).strip(),
            "signatory_contact": signatory_contact,
            "status": "Draft",
            "items": [
                {
                    "section": cstr(case.get("module"))[:140],
                    "question": cstr(case.get("title"))[:1000],
                    "help_text": "\n".join(
                        part
                        for part in (
                            cstr(case.get("steps")),
                            _("Expected: {0}").format(cstr(case.get("expected"))),
                        )
                        if part
                    )[:1000],
                }
                for case in cases
            ],
        }
    ).insert(ignore_permissions=True)
    return _sent_if_asked(doc, send)


def _uat_cases(project: str, cached: bool = False) -> dict:
    """The project's UAT tests from its plan's SRS on the ERP site. The mail preview asks
    `cached` (ten minutes), so typing in the dialog doesn't ask the ERP site each time;
    creating a UAT always reads them afresh."""
    plan = frappe.db.get_value("Project", project, "custom_crm_plan")
    if not plan:
        return {}
    key = f"signoff_uat_cases:{project}:{plan}"
    if cached and (found := frappe.cache.get_value(key)):
        return found
    found = _erp_call(project, "get_uat_cases", name=plan) or {}
    frappe.cache.set_value(key, found, expires_in_sec=600)
    return found


def _mail_fields(subject: str | None, body: str | None, cc: str | None) -> dict:
    return {
        "email_subject": cstr(subject).strip() or None,
        "email_body": body or None,
        "cc_emails": cstr(cc).strip() or None,
    }


def _sent_if_asked(doc, send: int | str) -> dict:
    """{name, status}; with `send`, the link goes out first (a failure rolls the new sign-off
    back with the request, and the dialog keeps what was typed)."""
    if cint(send):
        doc.send_link()
    return {"name": doc.name, "status": doc.status}


ERP_ATTEMPTS = 3


def record_uat_on_erp(signoff: str, status: str, signed_by: str | None = None) -> bool:
    """A UAT sign-off's state (as it was when queued) to its plan on the ERP site, which
    starts the warranty when Signed. The ERP site out of reach is tried again (three times,
    a few seconds apart); a failure that stays is written on the sign-off's history, and
    *Record on the ERP site* sends it again. Returns whether it was recorded."""
    import time

    from helpdesk.integrations.crm.leads import LeadsError, LeadsUnavailableError

    doc = frappe.get_doc(SIGNOFF, signoff)
    for attempt in range(1, ERP_ATTEMPTS + 1):
        try:
            _erp_call(
                doc.project,
                "record_uat",
                post=True,
                name=doc.crm_plan,
                status=status,
                signed_by=signed_by,
            )
            break
        except LeadsUnavailableError as e:
            if attempt == ERP_ATTEMPTS:
                return _not_recorded(doc, status, e)
            frappe.clear_messages()
            time.sleep(2 * attempt)
        except LeadsError as e:
            return _not_recorded(doc, status, e)
    doc.reload()
    doc.crm_recorded = status
    doc.flags.signoff_action = True
    doc.log_event(_("Recorded on the ERP site"), detail=_(status))
    doc.save(ignore_permissions=True)
    return True


def _not_recorded(doc, status: str, error) -> bool:
    frappe.clear_messages()
    doc.reload()
    doc.flags.signoff_action = True
    doc.log_event(
        _("Not recorded on the ERP site"),
        detail=_("{0}: {1}").format(_(status), str(error)),
    )
    doc.save(ignore_permissions=True)
    return False


@frappe.whitelist(methods=["POST"])
def record_uat_again(signoff: str) -> dict:
    """Send a UAT's current state to the ERP site again (after it couldn't be recorded)."""
    doc = _get_signoff(signoff, manage=True)
    if not doc.is_uat() or not doc.crm_plan:
        frappe.throw(_("Only a UAT made from a plan is recorded on the ERP site."))
    ok = record_uat_on_erp(
        doc.name, doc.status, doc.signer_name if doc.status == SIGNED else None
    )
    if not ok:
        frappe.throw(
            _(
                "The ERP site couldn't record it. The reason is in the history; try again later."
            )
        )
    return get_signoff(doc.name)


def _erp_call(project: str, method: str, post: bool = False, **params):
    """TBO Smart's hub proposals API on behalf of the person who made the project from the
    plan (`custom_crm_acting_user`: the ERP site already let them read that plan), whoever
    acts here: a project manager reading the tests, or the customer signing. The ERP site
    still checks that person's rights."""
    from helpdesk.api.proposals import PROPOSALS
    from helpdesk.integrations.crm.leads import call

    maker = frappe.db.get_value("Project", project, "custom_crm_acting_user")
    if not maker:
        frappe.throw(
            _(
                "This project doesn't say who made it from the plan, so the ERP site can't be asked. Press Create project on the lead's documents strip once more: it links the same project and records you."
            )
        )
    return call(method, post=post, api=PROPOSALS, acting_user=maker, **params)


@frappe.whitelist(methods=["POST"])
def update_signoff(
    signoff: str,
    module_title: str,
    signatory_contact: str,
    trainer: str,
    items: str | list,
    training_date: str | None = None,
    email_subject: str | None = None,
    email_body: str | None = None,
    cc_emails: str | None = None,
) -> dict:
    """Edit the details, mail and questions of a draft or reopened sign-off (the mail only
    when it is given, so an older client leaves it as it is)."""
    doc = _get_signoff(signoff, manage=True)
    if doc.status not in EDITABLE_STATUSES:
        frappe.throw(
            _(
                "Only a draft or reopened sign-off can be edited; this one is {0}."
            ).format(_(doc.status))
        )
    if not cstr(module_title).strip():
        frappe.throw(_("Name the module this sign-off is for, e.g. Accounts."))
    if not cstr(trainer).strip():
        frappe.throw(_("Pick the trainer who ran the training."))
    doc.module_title = cstr(module_title).strip()
    doc.training_date = training_date or None
    doc.trainer = cstr(trainer).strip()
    doc.signatory_contact = signatory_contact
    doc.set("items", _merge_items(doc, items))
    if email_subject is not None:
        doc.update(_mail_fields(email_subject, email_body, cc_emails))
    doc.log_event(_("Edited"))
    doc.save(ignore_permissions=True)
    return {"name": doc.name}


# --- the lead page (Documents card, the UAT step) ---


@frappe.whitelist()
def get_lead_signoff(lead: str) -> dict:
    """The UAT sign-off of the project made for `lead`, for the lead's Documents card: its
    status in the customer's terms, who signed, and what the person may do (send one when
    there is none, open it). Anyone who may see the lead sees the status."""
    access = _lead_access(lead)
    project = access.project
    if not project or not frappe.db.exists("Project", project):
        return {"project": None, "signoff": None, "can_send": False, "can_open": False}
    row = frappe.get_all(
        SIGNOFF,
        filters={"project": project, "signoff_type": UAT},
        fields=["name"],
        order_by="creation desc",
        limit=1,
    )
    signoff = None
    if row:
        doc = frappe.get_doc(SIGNOFF, row[0].name)
        signoff = {
            "name": doc.name,
            "status": doc.status,
            "customer_status": doc.customer_status(),
            "signatory_name": doc.signatory_name,
            "link_sent_on": doc.link_sent_on,
            "signed_on": doc.signed_on,
            "signer_name": doc.signer_name,
            "signer_designation": doc.signer_designation,
            "has_pdf": bool(doc.signed_pdf),
            "counts": doc.counts(),
        }
    plan = frappe.db.get_value("Project", project, "custom_crm_plan")
    return {
        "project": project,
        "signoff": signoff,
        "can_send": bool(plan) and (access.owner or can_manage_project(project)),
        "can_open": bool(frappe.has_permission("Project", "read", doc=project)),
    }


@frappe.whitelist(methods=["GET"])
def download_lead_signoff_pdf(lead: str):
    """The signed UAT record of the lead's project, to anyone who may see the lead: it is
    private on the project, which a salesperson may not open."""
    access = _lead_access(lead)
    found = (
        frappe.get_all(
            SIGNOFF,
            filters={"project": access.project, "signoff_type": UAT, "status": SIGNED},
            pluck="signed_pdf",
            order_by="signed_on desc",
            limit=1,
        )
        if access.project
        else []
    )
    if not found or not found[0]:
        frappe.throw(_("There is no signed record yet."), frappe.DoesNotExistError)
    file_doc = frappe.get_doc("File", found[0])
    frappe.local.response.filename = file_doc.file_name
    frappe.local.response.filecontent = file_doc.get_content()
    frappe.local.response.type = "download"


def note_signed_on_crm_lead(signoff: str, note: str) -> None:
    """Queued when a sign-off of a project made for a lead is signed: `note` on the lead's
    timeline on the ERP site, as the person who made the project from the plan (else whoever
    sent the link), and the lead's owner told. A failure is written on the sign-off's history;
    the customer never waits for it."""
    from helpdesk.integrations.crm.leads import LeadsError, call
    from helpdesk.work_reminders import notify_users

    doc = frappe.get_doc(SIGNOFF, signoff)
    lead, maker = frappe.db.get_value(
        "Project", doc.project, ["custom_crm_lead", "custom_crm_acting_user"]
    )
    acting = maker or doc.link_sent_by
    if not lead or not acting:
        return
    try:
        call("add_note", post=True, name=lead, note=note, acting_user=acting)
        detail = call("get_lead", name=lead, acting_user=acting) or {}
    except LeadsError as e:
        frappe.clear_messages()
        doc.reload()
        doc.flags.signoff_action = True
        doc.log_event(_("Not noted on the lead"), detail=str(e))
        doc.save(ignore_permissions=True)
        return
    owner = (detail.get("lead") or {}).get("lead_owner")
    if owner and owner not in (doc.link_sent_by, doc.project_lead()):
        notify_users(
            [owner],
            SIGNOFF,
            doc.name,
            note,
            link=f"/leads/{lead}",
            once=False,
        )


@frappe.whitelist(methods=["POST"])
def send_signoff_link(signoff: str) -> dict:
    """Email the signatory a new link; any earlier link stops working."""
    doc = _get_signoff(signoff, manage=True)
    doc.send_link(resend=bool(doc.link_sent_on))
    return {"status": doc.status, "link_expires_on": doc.link_expires_on}


@frappe.whitelist(methods=["POST"])
def revoke_signoff_link(signoff: str) -> dict:
    doc = _get_signoff(signoff, manage=True)
    doc.revoke_link()
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def mark_item_clarified(signoff: str, item: str, note: str = "") -> dict:
    """The trainer explained the item; it goes back to the customer, who gets a fresh link."""
    doc = _get_signoff(signoff, manage=True)
    doc.clarify(cstr(item), cstr(note))
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def reopen_signoff(signoff: str, reason: str) -> dict:
    doc = _get_signoff(signoff, manage=True)
    doc.reopen(cstr(reason))
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def delete_signoff(signoff: str) -> None:
    """Only a draft, which the customer has never seen, can be deleted."""
    doc = _get_signoff(signoff, manage=True)
    if doc.status != "Draft":
        frappe.throw(
            _("Only a draft sign-off can be deleted. Revoke the link instead.")
        )
    frappe.delete_doc(SIGNOFF, doc.name, ignore_permissions=True)


# --- templates ---


@frappe.whitelist()
def get_signoff_templates() -> list[dict]:
    """Every template, active first, with its question count."""
    _check_template_manager()
    template = frappe.qb.DocType(TEMPLATE)
    item = frappe.qb.DocType("HD Signoff Template Item")
    count = Count(item.name)
    return (
        frappe.qb.from_(template)
        .left_join(item)
        .on((item.parent == template.name) & (item.parenttype == TEMPLATE))
        .select(
            template.name,
            template.template_name,
            template.module,
            template.description,
            template.is_active,
            template.signoff_type,
            template.project_type,
            count.as_("question_count"),
        )
        .groupby(template.name)
        .orderby(template.is_active, order=frappe.qb.desc)
        .orderby(template.template_name)
        .run(as_dict=True)
    )


@frappe.whitelist()
def get_signoff_template(template: str) -> dict:
    _check_template_manager()
    doc = frappe.get_doc(TEMPLATE, template)
    return {
        "name": doc.name,
        "template_name": doc.template_name,
        "module": doc.module,
        "description": doc.description,
        "is_active": doc.is_active,
        "signoff_type": doc.signoff_type,
        "project_type": doc.project_type,
        "email_subject": doc.email_subject,
        "email_body": doc.email_body,
        "default_cc": doc.default_cc,
        "items": [
            {
                "name": row.name,
                "section": row.section,
                "question": row.question,
                "help_text": row.help_text,
            }
            for row in doc.items
        ],
    }


@frappe.whitelist(methods=["POST"])
def save_signoff_template(
    template_name: str,
    items: str | list,
    module: str = "",
    description: str = "",
    is_active: bool = True,
    template: str | None = None,
    signoff_type: str = TRAINING,
    project_type: str = "",
    email_subject: str = "",
    email_body: str = "",
    default_cc: str = "",
) -> dict:
    """Create a template (no `template`) or replace an existing one's details, mail and
    questions."""
    _check_template_manager()
    doc = frappe.get_doc(TEMPLATE, template) if template else frappe.new_doc(TEMPLATE)
    if not template:
        doc.template_name = cstr(template_name).strip()
    elif cstr(template_name).strip() != doc.template_name:
        frappe.throw(
            _("A template's name can't be changed. Make a new template instead.")
        )
    doc.module = cstr(module).strip()
    doc.description = cstr(description).strip()
    doc.is_active = 1 if frappe.utils.sbool(is_active) else 0
    doc.signoff_type = UAT if signoff_type == UAT else TRAINING
    doc.project_type = cstr(project_type).strip() or None
    doc.email_subject = cstr(email_subject).strip() or None
    doc.email_body = email_body or None
    doc.default_cc = cstr(default_cc).strip() or None
    doc.set("items", _parse_items(items))
    doc.save(ignore_permissions=True)
    return {"name": doc.name}


# --- helpers ---


def _check_project(project: str) -> str:
    project = cstr(project)
    if not frappe.db.exists("Project", project):
        frappe.throw(
            _("Project not found: {0}").format(project), frappe.DoesNotExistError
        )
    frappe.has_permission("Project", "read", doc=project, throw=True)
    return project


LEAD_ACCESS_TTL = 600


def _lead_access(lead: str) -> frappe._dict:
    """What the ERP site says of this person and `lead`: that they may see it (else it throws,
    as the lead page does, a salesperson's own leads only), the hub project made for it (the
    document chain's Project step) and whether they own it. Kept ten minutes per person and
    lead, so the lead page can follow the sign-off's status without asking the ERP site each
    time."""
    from helpdesk.api.leads import get_lead

    lead = cstr(lead)
    key = f"signoff_lead_access:{frappe.session.user}:{lead}"
    cached = frappe.cache.get_value(key)
    if cached:
        return frappe._dict(cached)
    detail = get_lead(lead)
    steps = (detail.get("documents") or {}).get("steps") or []
    access = {
        "project": next(
            (
                s.get("name")
                for s in steps
                if s.get("document_type") == "Project" and s.get("name")
            ),
            None,
        ),
        "owner": (detail.get("lead") or {}).get("lead_owner") == frappe.session.user,
    }
    frappe.cache.set_value(key, access, expires_in_sec=LEAD_ACCESS_TTL)
    return frappe._dict(access)


def _project_for(project: str, lead: str | None = None, manage: bool = False) -> str:
    """The project, if this person may use it here: through the project (read; `manage`: its
    managers and lead), or from `lead`'s page, whose project it must be, by the lead's owner
    or the project's managers."""
    project = cstr(project)
    if not lead:
        project = _check_project(project)
        if manage and not can_manage_project(project):
            frappe.throw(
                _("Only the project's manager or lead can add sign-offs."),
                frappe.PermissionError,
            )
        return project
    access = _lead_access(lead)
    if access.project != project or not frappe.db.exists("Project", project):
        frappe.throw(_("That project isn't this lead's."), frappe.PermissionError)
    if (manage or not frappe.has_permission("Project", "read", doc=project)) and not (
        access.owner or can_manage_project(project)
    ):
        frappe.throw(
            _(
                "Only the lead's owner, or the project's manager or lead, can send its sign-off."
            ),
            frappe.PermissionError,
        )
    return project


def _check_template(template: str | None, signoff_type: str):
    if not template:
        return
    active, kind = frappe.db.get_value(
        TEMPLATE, template, ["is_active", "signoff_type"]
    ) or (0, None)
    if not active:
        frappe.throw(_("Template {0} isn't active.").format(template))
    if (kind or TRAINING) != signoff_type:
        frappe.throw(
            _("Template {0} is for a {1} sign-off.").format(
                template, _(kind or TRAINING)
            )
        )


def _viewed_since_sent(signoffs: list) -> set[str]:
    """The Sent sign-offs whose customer opened the link (verified their code) since it was
    last sent."""
    sent = {
        s.name: s.link_sent_on for s in signoffs if s.status == SENT and s.link_sent_on
    }
    if not sent:
        return set()
    log = frappe.qb.DocType("HD Project Signoff Log")
    rows = (
        frappe.qb.from_(log)
        .select(log.parent, Max(log.at).as_("opened"))
        .where(log.parenttype == SIGNOFF)
        .where(log.parent.isin(list(sent)))
        .where(log.event == _("Code verified"))
        .groupby(log.parent)
        .run(as_dict=True)
    )
    return {
        r.parent
        for r in rows
        if r.opened and get_datetime(r.opened) >= get_datetime(sent[r.parent])
    }


def _get_signoff(signoff: str, manage: bool = False):
    """The sign-off, if the user can read its project; with `manage`, only for those who run it."""
    signoff = cstr(signoff)
    if not frappe.db.exists(SIGNOFF, signoff):
        frappe.throw(_("Sign-off not found"), frappe.DoesNotExistError)
    doc = frappe.get_doc(SIGNOFF, signoff)
    _check_project(doc.project)
    if manage and not _can_manage(doc):
        frappe.throw(
            _("Only the project's manager or lead, or the trainer, can do this."),
            frappe.PermissionError,
        )
    return doc


def _can_manage(doc) -> bool:
    return doc.trainer == frappe.session.user or can_manage_project(doc.project)


def _check_template_manager():
    # frappe.only_for is skipped in tests, so check the role directly
    if not is_project_manager():
        frappe.throw(
            _("Only project managers can manage sign-off templates."),
            frappe.PermissionError,
        )


def _active_templates() -> list[dict]:
    template = frappe.qb.DocType(TEMPLATE)
    return (
        frappe.qb.from_(template)
        .select(
            template.name,
            template.template_name,
            template.module,
            template.signoff_type,
            template.project_type,
        )
        .where(template.is_active == 1)
        .orderby(template.template_name)
        .run(as_dict=True)
    )


def _customer_contacts(customer: str) -> list[dict]:
    """The customer's contacts that have an email: the people who can sign."""
    member = frappe.qb.DocType("HD Customer Member")
    contact = frappe.qb.DocType("Contact")
    rows = (
        frappe.qb.from_(member)
        .join(contact)
        .on(contact.name == member.contact_name)
        .select(contact.name, contact.full_name, contact.email_id, contact.designation)
        .where(member.parenttype == "HD Customer")
        .where(member.parent == customer)
        .where(contact.email_id.isnotnull())
        .where(contact.email_id != "")
        .orderby(contact.full_name)
        .run(as_dict=True)
    )
    return [
        {
            "contact": r.name,
            "full_name": r.full_name or r.email_id,
            "email": r.email_id,
            "designation": r.designation,
        }
        for r in rows
    ]


def _item_counts(signoffs: list[str]) -> dict:
    """{sign-off: {total, done, follow_up}}"""
    if not signoffs:
        return {}
    item = frappe.qb.DocType("HD Project Signoff Item")
    rows = (
        frappe.qb.from_(item)
        .select(item.parent, item.response)
        .where(item.parenttype == SIGNOFF)
        .where(item.parent.isin(signoffs))
        .run(as_dict=True)
    )
    counts: dict = {}
    for r in rows:
        c = counts.setdefault(r.parent, {"total": 0, "done": 0, "follow_up": 0})
        c["total"] += 1
        c["done"] += r.response == "Done"
        c["follow_up"] += r.response in NEEDS_FOLLOW_UP
    return counts


def _file_info(name: str) -> dict | None:
    return frappe.db.get_value(
        "File", name, ["name", "file_name", "file_url"], as_dict=True
    )


def _parse_items(items: str | list) -> list[dict]:
    rows = frappe.parse_json(items) if isinstance(items, str) else items
    return [
        {
            "section": cstr(r.get("section")).strip(),
            "question": cstr(r.get("question")).strip(),
            "help_text": cstr(r.get("help_text")).strip(),
        }
        for r in rows or []
        if isinstance(r, dict)
    ]


def _merge_items(doc, items: str | list) -> list:
    """The edited question list; rows that keep their name keep their answers."""
    existing = {row.name: row for row in doc.items}
    rows = frappe.parse_json(items) if isinstance(items, str) else items
    merged = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        values = {
            "section": cstr(r.get("section")).strip(),
            "question": cstr(r.get("question")).strip(),
            "help_text": cstr(r.get("help_text")).strip(),
        }
        row = existing.get(cstr(r.get("name")))
        if row:
            # a reworded question is a new question: its old answer and follow-up no longer apply
            if row.question != values["question"]:
                values.update(RESET_ANSWER)
            row.update(values)
            merged.append(row)
        else:
            merged.append(values)
    return merged

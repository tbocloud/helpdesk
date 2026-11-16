"""Sign-offs on a project (Project -> Sign-off tab, the full sign-off page, and the lead
page's Documents card) and their templates.

Who does what follows TBO's Sign-off requirements (Roles): everyone who can read the project
sees its sign-offs; its managers and lead, its coordinators, its team members and System
Managers create and save drafts; only the managers, lead, coordinators and System Managers send,
remind and mark signed off or changes requested; only a System Manager cancels a signed-off one
and manages templates. The trainer also marks items clarified, and the owner of the lead the
project was made for sends its UAT from the lead page. Customers never use these endpoints;
they answer on the token page (helpdesk.api.signoff_portal) and accept by replying to the mail.
See docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count, Max
from frappe.utils import cint, cstr, get_datetime, get_fullname

from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    CANCELLED,
    CODE_VERIFIED,
    DETAIL_FIELDS,
    DETAIL_LABELS,
    DETAIL_TABLES,
    DRAFT,
    EDITABLE_STATUSES,
    NEEDS_FOLLOW_UP,
    SENT,
    SIGNED_OFF,
    TRAINING,
    UAT,
    HDProjectSignoff,
)
from helpdesk.helpdesk.doctype.hd_signoff_template.hd_signoff_template import (
    ERPNEXT_MODULES,
    PLATFORMS,
    SECTIONS,
    SERVICES,
    STAGES,
    TRAINING_STAGE,
)
from helpdesk.tasky.permissions import (
    can_manage_project,
    get_project_team,
    is_project_coordinator,
)

SIGNOFF = "HD Project Signoff"
# history events the page reads back: stored as is, whatever the language of the request
RECORDED_ON_ERP = "Recorded on the ERP site"
NOT_RECORDED_ON_ERP = "Not recorded on the ERP site"
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
            "stage",
            "template",
            "status",
            "training_date",
            "trainer",
            "signatory_name",
            "signatory_email",
            "link_sent_on",
            "signed_on",
            "remarks",
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
    # the completion letter is the trainings': a UAT, another stage or a cancelled one isn't
    # in its roll-up (HDProjectSignoff.project_signoffs)
    training = [
        s
        for s in signoffs
        if s.signoff_type != UAT
        and s.stage in (None, "", TRAINING_STAGE)
        and s.status != CANCELLED
    ]
    signed = sum(1 for s in training if s.status == SIGNED_OFF)
    return {
        "signoffs": signoffs,
        "signed": signed,
        "total": len(training),
        "completion_letter": (
            _file_info(letter)
            if letter and training and signed == len(training)
            else None
        ),
        "can_create": _can_create(project),
        # made from an implementation plan on the ERP site: its SRS gives the UAT's tests
        "can_create_uat": bool(plan) and _can_create(project),
    }


@frappe.whitelist()
def get_signoff_form(project: str, lead: str | None = None) -> dict:
    """What the New sign-off dialog offers: the project's type, active templates, the team
    (trainers), the customer (name, addresses with the primary first, contacts with an email,
    the default signatory) and who is copied by default (the project lead and you). `lead`:
    opened from that lead's page, by someone who may not read the project but owns the lead."""
    project = _project_for(project, lead)
    info = frappe.db.get_value(
        "Project",
        project,
        ["project_name", "customer", "project_type", "project_lead", "custom_crm_plan"],
        as_dict=True,
    )
    me = frappe.session.user
    contacts = _customer_contacts(info.customer) if info.customer else []
    return {
        "project_name": info.project_name or project,
        "project_type": info.project_type,
        "customer": info.customer,
        "customer_name": (
            frappe.db.get_value("HD Customer", info.customer, "customer_name")
            or info.customer
        )
        if info.customer
        else None,
        "addresses": _customer_addresses(info.customer) if info.customer else [],
        "default_contact": next(
            (c["contact"] for c in contacts if c["is_primary"]),
            contacts[0]["contact"] if len(contacts) == 1 else None,
        ),
        "can_send": _can_send(project) or bool(lead),
        "templates": _active_templates(),
        "team": [
            {"user": u, "full_name": get_fullname(u)} for u in get_project_team(project)
        ],
        "contacts": contacts,
        "default_cc": [
            e
            for e in dict.fromkeys((info.project_lead, me))
            if e and e not in ("Administrator", "Guest")
        ],
        # made from an implementation plan on the ERP site: its SRS gives the UAT's tests
        "can_create_uat": bool(info.custom_crm_plan),
        # a placeholder left in the mail is named in the words of the field that fills it
        "placeholder_labels": HDProjectSignoff.placeholder_labels(),
        # what each stage shows and needs (TBO's Sign-off requirements), and its choices
        "stages": STAGES,
        "sections": SECTIONS,
        "services": SERVICES,
        "platforms": PLATFORMS,
        "erpnext_modules": ERPNEXT_MODULES,
        "detail_labels": {field: _(label) for field, label in DETAIL_LABELS.items()},
        # a UAT's modules start as every module in the project's scope
        "project_modules": _project_modules(project),
        "fields": _detail_meta(),
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
    customer_address: str | None = None,
    details: str | dict | None = None,
) -> dict:
    """The mail the dialog fills in: the template's (or the standard) subject and body with
    what is known so far, its CC, and the placeholders still `missing` (they hold the mail
    back). Nothing is saved."""
    project = _project_for(project, lead)
    doc = _unsaved_signoff(
        project,
        {
            "signoff_type": signoff_type,
            "template": template,
            "module_title": module_title,
            "training_date": training_date,
            "trainer": trainer,
            "signatory_contact": signatory_contact,
            "customer_address": customer_address,
            "details": details,
        },
    )
    if doc.is_uat() and not doc.modules:
        # the modules a UAT covers are its tests' sections
        for case in _uat_cases(project, cached=True).get("cases") or []:
            doc.append("items", {"section": cstr(case.get("module"))})
    return doc.render_mail()


@frappe.whitelist(methods=["POST"])
def preview_new_signoff_document(
    project: str, values: str | dict, lead: str | None = None
) -> str:
    """The sign-off document as HTML for a sign-off not saved yet (the full page's Document
    preview while it is being written). Nothing is saved."""
    project = _project_for(project, lead)
    values = frappe.parse_json(values) if isinstance(values, str) else values or {}
    doc = _unsaved_signoff(project, values)
    doc.set("items", _parse_items(values.get("items") or []))
    for i, row in enumerate(doc.items, start=1):
        row.idx = i
    return doc.render_html(doc.document_context())


@frappe.whitelist()
def get_template_questions(
    project: str, template: str, lead: str | None = None
) -> list[dict]:
    """A template's questions, for the full page's questions editor before the sign-off is
    saved (those who add sign-offs; managing templates is a System Manager's)."""
    _project_for(project, lead)
    return _parse_items(
        frappe.get_all(
            "HD Signoff Template Item",
            filters={"parenttype": TEMPLATE, "parent": cstr(template)},
            fields=["section", "question", "help_text"],
            order_by="idx asc",
        )
    )


def _unsaved_signoff(project: str, values: dict):
    """A sign-off in memory with what the form has so far, to fill its mail or document in."""

    def get(key: str) -> str | None:
        return cstr(values.get(key)).strip() or None

    # new_doc: the fields' defaults (ERPNext version "V16") apply until the form says otherwise
    doc = frappe.new_doc(SIGNOFF)
    doc.update(
        {
            "project": project,
            "signoff_type": UAT if values.get("signoff_type") == UAT else TRAINING,
            "template": get("template"),
            "module_title": get("module_title") or "",
            "training_date": get("training_date"),
            "trainer": get("trainer"),
            "signatory_contact": get("signatory_contact"),
            "customer_address": get("customer_address"),
            "cc_emails": get("cc_emails"),
            **_detail_values(values.get("details")),
        }
    )
    if doc.template:
        doc.stage, doc.declaration = frappe.db.get_value(
            TEMPLATE, doc.template, ["stage", "declaration_text"]
        ) or (None, None)
    doc.project_name = frappe.db.get_value("Project", project, "project_name")
    doc.customer = frappe.db.get_value("Project", project, "customer")
    if doc.signatory_contact:
        contact = doc.contact_details(doc.signatory_contact)
        if contact:
            doc.signatory_name = contact.full_name
            doc.signatory_email = contact.email_id
            doc.signatory_designation = contact.designation
    return doc


@frappe.whitelist()
def get_signoff(signoff: str) -> dict:
    doc = _get_signoff(signoff)
    can_edit = _can_create(doc.project) and doc.status in EDITABLE_STATUSES
    return {
        "name": doc.name,
        "project": doc.project,
        "project_name": doc.project_name,
        "project_type": doc.project_type,
        "customer": doc.customer,
        "customer_name": doc.customer_name() if doc.customer else None,
        "customer_address": doc.customer_address,
        # as sent; until then, the address as it reads now
        "address_display": doc.address_display or doc.formatted_address(),
        "module_title": doc.module_title,
        "signoff_type": doc.signoff_type,
        # a UAT's state on the ERP site; differs from `status` until recorded
        "crm_recorded": doc.crm_recorded,
        # the ERP site refused or was out of reach since: "Record on the ERP site" is offered
        "crm_failed": _erp_record_failed(doc),
        "template": doc.template,
        "status": doc.status,
        "customer_status": doc.customer_status(),
        "email_subject": doc.email_subject,
        "email_body": doc.email_body,
        "cc_emails": doc.cc_emails,
        "attach_pdf": doc.attach_pdf,
        "sent_pdf": _file_info(doc.sent_pdf) if doc.sent_pdf else None,
        "remarks": doc.remarks,
        "reminder_sent_on": doc.reminder_sent_on,
        "training_date": doc.training_date,
        "trainer": doc.trainer,
        "trainer_name": get_fullname(doc.trainer) if doc.trainer else None,
        "signatory_contact": doc.signatory_contact,
        "signatory_name": doc.signatory_name,
        "signatory_email": doc.signatory_email,
        "signatory_designation": doc.signatory_designation,
        "link_open": doc.link_is_open(),
        "link_sent_on": doc.link_sent_on,
        "link_expires_on": doc.link_expires_on if doc.link_token_hash else None,
        "signed_on": doc.signed_on,
        "signer_name": doc.signer_name,
        "signer_designation": doc.signer_designation,
        "signer_email": doc.signer_email,
        "signed_off_by": doc.signed_off_by,
        "acceptance_reference": doc.acceptance_reference,
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
        "stage": doc.stage,
        "declaration": doc.declaration,
        "signed_copy": doc.signed_copy,
        "shown_sections": list(doc.shown_sections()),
        "details": _details_of(doc),
        "can_edit": can_edit,
        "can_send": _can_send(doc.project),
        "can_clarify": _can_clarify(doc),
        "can_cancel": _is_system_manager() and doc.status != CANCELLED,
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
    customer_address: str | None = None,
    attach_pdf: int | str = 1,
    items: str | list | None = None,
    details: str | dict | None = None,
) -> dict:
    """A training sign-off, saved as a draft, or (`send`) sent to the customer at once with its
    mail; a send that fails saves nothing. `items` (from the full page) are its questions;
    without them, the template's are copied in."""
    project = _project_for(project, lead, manage=True)
    _check_lead_sends(lead, send)
    _check_template(template, TRAINING)
    doc = frappe.get_doc(
        {
            "doctype": SIGNOFF,
            "project": project,
            "template": template or None,
            "module_title": cstr(module_title).strip(),
            "training_date": training_date or None,
            "trainer": cstr(trainer).strip(),
            "signatory_contact": signatory_contact,
            "status": DRAFT,
            **_mail_fields(email_subject, email_body, cc_emails),
            **_document_fields(customer_address, attach_pdf),
            **_detail_values(details),
            "items": _parse_items(items) if items else [],
        }
    ).insert(ignore_permissions=True)
    return _sent_if_asked(doc, send, lead)


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
    customer_address: str | None = None,
    attach_pdf: int | str = 1,
    details: str | dict | None = None,
) -> dict:
    """A UAT sign-off for a project made from an implementation plan: a test case for
    each functional requirement of the plan's approved SRS on the ERP site (its module the
    section, its steps and expected result the help text). A draft, edited and sent like
    any sign-off, or (`send`) sent at once with its mail."""
    project = _project_for(project, lead, manage=True)
    _check_lead_sends(lead, send)
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
            **_document_fields(customer_address, attach_pdf),
            **_uat_details(details, cases),
            "module_title": _("User acceptance testing ({0})").format(
                found.get("srs") or plan
            )[:140],
            "trainer": cstr(trainer).strip(),
            "signatory_contact": signatory_contact,
            "status": DRAFT,
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
    return _sent_if_asked(doc, send, lead)


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


def _document_fields(customer_address: str | None, attach_pdf: int | str) -> dict:
    return {
        "customer_address": cstr(customer_address).strip() or None,
        "attach_pdf": 1 if cint(attach_pdf) else 0,
    }


def _sent_if_asked(doc, send: int | str, lead: str | None = None) -> dict:
    """{name, status}; with `send`, the mail goes out first (a failure rolls the new sign-off
    back with the request, and the dialog keeps what was typed). From the lead page, its owner
    may send its UAT; otherwise only those who send sign-offs (`_can_send`)."""
    if cint(send):
        if not lead and not _can_send(doc.project):
            frappe.throw(
                _(
                    "Only the project's managers, lead or coordinators can send a sign-off. Save it as a draft."
                ),
                frappe.PermissionError,
            )
        doc.send_mail()
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
    doc.log_event(RECORDED_ON_ERP, detail=_(status))
    doc.save(ignore_permissions=True)
    return True


def _erp_record_failed(doc) -> bool:
    """A UAT whose latest try to record it on the ERP site failed (not one still queued)."""
    tries = [
        row.event
        for row in doc.log
        if row.event in (RECORDED_ON_ERP, NOT_RECORDED_ON_ERP)
    ]
    return bool(tries) and tries[-1] == NOT_RECORDED_ON_ERP


def _not_recorded(doc, status: str, error) -> bool:
    frappe.clear_messages()
    doc.reload()
    doc.flags.signoff_action = True
    doc.log_event(
        NOT_RECORDED_ON_ERP,
        detail=_("{0}: {1}").format(_(status), str(error)),
    )
    doc.save(ignore_permissions=True)
    return False


@frappe.whitelist(methods=["POST"])
def record_uat_again(signoff: str) -> dict:
    """Send a UAT's current state to the ERP site again (after it couldn't be recorded)."""
    doc = _get_signoff(signoff, need="send")
    if not doc.is_uat() or not doc.crm_plan:
        frappe.throw(_("Only a UAT made from a plan is recorded on the ERP site."))
    if not doc.erp_state():
        frappe.throw(
            _("Only a signed-off or cancelled UAT is recorded on the ERP site.")
        )
    ok = record_uat_on_erp(
        doc.name,
        doc.erp_state(),
        doc.signer_name if doc.status == SIGNED_OFF else None,
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
    customer_address: str | None = None,
    attach_pdf: int | str = 1,
    details: str | dict | None = None,
) -> dict:
    """Edit the details, mail and questions of a draft (or changes requested) sign-off."""
    doc = _get_signoff(signoff, need="edit")
    if doc.status not in EDITABLE_STATUSES:
        frappe.throw(
            _(
                "Only a draft, or a sign-off the customer asked to change, can be edited; this one is {0}."
            ).format(_(doc.status))
        )
    doc.module_title = cstr(module_title).strip()
    doc.training_date = training_date or None
    doc.trainer = cstr(trainer).strip() or None
    doc.signatory_contact = signatory_contact
    doc.set("items", _merge_items(doc, items))
    doc.update(_mail_fields(email_subject, email_body, cc_emails))
    doc.update(_document_fields(customer_address, attach_pdf))
    if details is not None:
        doc.update(_detail_values(details))
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
        "can_send": bool(plan) and (access.owner or _can_send(project)),
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
            filters={
                "project": access.project,
                "signoff_type": UAT,
                "status": SIGNED_OFF,
            },
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
    """Queued when a sign-off of a project made for a lead is signed off: `note` on the lead's
    timeline on the ERP site, as the person who made the project from the plan (else whoever
    sent the mail), and the lead's owner told. A failure is written on the sign-off's history;
    nobody waits for it."""
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
def send_signoff(signoff: str) -> dict:
    """Send the sign-off mail to the customer (a draft, or after changes were requested)."""
    doc = _get_signoff(signoff, need="send")
    doc.send_mail()
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def send_signoff_reminder(signoff: str) -> dict:
    """The same mail again with "Reminder:"; the status stays Sent."""
    doc = _get_signoff(signoff, need="send")
    doc.send_reminder()
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def mark_signed_off(
    signoff: str,
    acceptance_reference: str | None = None,
    signed_on: str | None = None,
    signed_off_by: str | None = None,
    signed_copy: str | None = None,
) -> dict:
    """The customer accepted (by replying, or with a signed copy): record who, when, and the
    evidence; the signed PDF goes on the project."""
    doc = _get_signoff(signoff, need="send")
    doc.sign_off(
        cstr(acceptance_reference).strip() or None,
        signed_on or None,
        cstr(signed_off_by).strip() or None,
        cstr(signed_copy).strip() or None,
    )
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def mark_changes_requested(signoff: str, remarks: str) -> dict:
    doc = _get_signoff(signoff, need="send")
    doc.mark_changes_requested(cstr(remarks))
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def cancel_signoff(signoff: str, reason: str) -> dict:
    """Only a System Manager cancels a sign-off (a signed-off one is otherwise final)."""
    doc = _get_signoff(signoff)
    if not _is_system_manager():
        frappe.throw(
            _("Only a System Manager can cancel a sign-off."), frappe.PermissionError
        )
    doc.cancel(cstr(reason))
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def revoke_signoff_link(signoff: str) -> dict:
    """Stop the questions page's link at once."""
    doc = _get_signoff(signoff, need="send")
    doc.revoke_link()
    doc.save(ignore_permissions=True)
    return {"status": doc.status}


@frappe.whitelist(methods=["POST"])
def mark_item_clarified(signoff: str, item: str, note: str = "") -> dict:
    """The trainer explained the item; it goes back to the customer, who gets a fresh link."""
    doc = _get_signoff(signoff, need="clarify")
    doc.clarify(cstr(item), cstr(note))
    return {"status": doc.status}


@frappe.whitelist()
def get_signoff_mails(signoff: str) -> list[dict]:
    """Every mail sent and received in the sign-off's thread, newest first (View mail
    history), with its attachments."""
    doc = _get_signoff(signoff)
    mails = frappe.get_all(
        "Communication",
        filters={"reference_doctype": SIGNOFF, "reference_name": doc.name},
        fields=[
            "name",
            "subject",
            "content",
            "sender",
            "sender_full_name",
            "recipients",
            "cc",
            "sent_or_received",
            "communication_date",
            "delivery_status",
        ],
        order_by="communication_date desc",
        limit_page_length=0,
    )
    files = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Communication",
            "attached_to_name": ("in", [m.name for m in mails] or [""]),
        },
        fields=["name", "file_name", "file_url", "attached_to_name"],
    )
    for m in mails:
        m.attachments = [f for f in files if f.attached_to_name == m.name]
    return mails


@frappe.whitelist()
def preview_signoff_document(signoff: str) -> str:
    """The sign-off document as HTML, as it goes out with the mail (Document preview)."""
    doc = _get_signoff(signoff)
    return doc.render_html(doc.document_context())


@frappe.whitelist(methods=["POST"])
def delete_signoff(signoff: str) -> None:
    """Only a draft, which the customer has never seen, can be deleted."""
    doc = _get_signoff(signoff, need="edit")
    if doc.status != DRAFT:
        frappe.throw(
            _("Only a draft sign-off can be deleted. A System Manager can cancel it.")
        )
    frappe.delete_doc(SIGNOFF, doc.name, ignore_permissions=True)
    if doc.is_training() and not frappe.db.get_value(
        "Project", doc.project, "custom_signoff_letter"
    ):
        # it may have been the last training not signed off: the completion letter is due now
        for name in frappe.get_all(
            SIGNOFF,
            filters={
                "project": doc.project,
                "signoff_type": ("!=", UAT),
                "status": SIGNED_OFF,
            },
            pluck="name",
        ):
            signed = frappe.get_doc(SIGNOFF, name)
            if signed.is_training():
                signed.complete_project_if_all_signed()
                break


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
            template.stage,
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
        "stage": doc.stage,
        "declaration_text": doc.declaration_text,
        "attach_pdf_default": doc.attach_pdf_default,
        "print_format": doc.print_format,
        "stages": list(STAGES),
        "print_formats": frappe.get_all(
            "Print Format",
            filters={"doc_type": SIGNOFF, "disabled": 0},
            pluck="name",
        ),
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
    stage: str = "",
    declaration_text: str = "",
    attach_pdf_default: int | str = 1,
    print_format: str = "",
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
    doc.stage = cstr(stage).strip() or None
    doc.declaration_text = cstr(declaration_text).strip() or None
    doc.attach_pdf_default = 1 if cint(attach_pdf_default) else 0
    doc.print_format = cstr(print_format).strip() or None
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
        if manage and not _can_create(project):
            frappe.throw(
                _(
                    "Only the project's managers, lead, coordinators and team can add sign-offs."
                ),
                frappe.PermissionError,
            )
        return project
    access = _lead_access(lead)
    if access.project != project or not frappe.db.exists("Project", project):
        frappe.throw(_("That project isn't this lead's."), frappe.PermissionError)
    if (manage or not frappe.has_permission("Project", "read", doc=project)) and not (
        access.owner or _can_send(project)
    ):
        frappe.throw(
            _(
                "Only the lead's owner, or the project's manager or lead, can send its sign-off."
            ),
            frappe.PermissionError,
        )
    return project


def _check_lead_sends(lead: str | None, send: int | str):
    """From the lead page a sign-off goes out at once: a draft there would be stranded, since
    the lead's owner may not open the project to send it."""
    if lead and not cint(send):
        frappe.throw(
            _("From the lead page a sign-off is sent at once, not kept as a draft.")
        )


def _check_template(template: str | None, signoff_type: str):
    if not template:
        return
    active, kind = frappe.db.get_value(
        TEMPLATE, template, ["is_active", "signoff_type"]
    ) or (0, None)
    if not active:
        frappe.throw(_("Template {0} isn't active.").format(template))
    # a UAT from the SRS needs a UAT template; any template starts an ordinary sign-off
    if signoff_type == UAT and (kind or TRAINING) != UAT:
        frappe.throw(
            _("Template {0} isn't a UAT template; pick one for UAT.").format(template)
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
        .where(log.event == CODE_VERIFIED)
        .groupby(log.parent)
        .run(as_dict=True)
    )
    return {
        r.parent
        for r in rows
        if r.opened and get_datetime(r.opened) >= get_datetime(sent[r.parent])
    }


def _get_signoff(signoff: str, need: str | None = None):
    """The sign-off, if the user can read its project; with `need` ("edit", "send",
    "clarify"), only for those who may do that (TBO's Sign-off requirements, Roles)."""
    signoff = cstr(signoff)
    if not frappe.db.exists(SIGNOFF, signoff):
        frappe.throw(_("Sign-off not found"), frappe.DoesNotExistError)
    doc = frappe.get_doc(SIGNOFF, signoff)
    _check_project(doc.project)
    allowed = {
        None: lambda: True,
        "edit": lambda: _can_create(doc.project),
        "send": lambda: _can_send(doc.project),
        "clarify": lambda: _can_clarify(doc),
    }[need]
    if not allowed():
        frappe.throw(
            {
                "edit": _(
                    "Only the project's managers, lead, coordinators and team can edit sign-offs."
                ),
                "send": _(
                    "Only the project's managers, lead or coordinators can do this."
                ),
                "clarify": _(
                    "Only the trainer, or the project's managers, lead or coordinators, can do this."
                ),
            }[need],
            frappe.PermissionError,
        )
    return doc


def _is_system_manager() -> bool:
    user = frappe.session.user
    return user == "Administrator" or "System Manager" in frappe.get_roles(user)


def _can_send(project: str) -> bool:
    """Send, remind, mark signed off or changes requested: the project's managers and lead,
    its coordinators, System Managers."""
    return (
        _is_system_manager()
        or can_manage_project(project)
        or is_project_coordinator(project)
    )


def _can_create(project: str) -> bool:
    """Create and save drafts: those who send, and the project's team (a trainer)."""
    return _can_send(project) or frappe.session.user in get_project_team(project)


def _can_clarify(doc) -> bool:
    return doc.trainer == frappe.session.user or _can_send(doc.project)


def _check_template_manager():
    # frappe.only_for is skipped in tests, so check the role directly
    if not _is_system_manager():
        frappe.throw(
            _("Only a System Manager can manage sign-off templates."),
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
            template.stage,
            template.attach_pdf_default,
            template.default_cc,
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
        .select(
            contact.name,
            contact.full_name,
            contact.email_id,
            contact.designation,
            contact.is_primary_contact,
        )
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
            "is_primary": bool(r.is_primary_contact),
        }
        for r in rows
    ]


def _customer_addresses(customer: str) -> list[dict]:
    """The customer's addresses (Frappe's, linked to the HD Customer), the primary first,
    then billing ones, each with how it reads."""
    from frappe.contacts.doctype.address.address import render_address

    address = frappe.qb.DocType("Address")
    link = frappe.qb.DocType("Dynamic Link")
    rows = (
        frappe.qb.from_(address)
        .join(link)
        .on((link.parent == address.name) & (link.parenttype == "Address"))
        .select(
            address.name,
            address.address_title,
            address.address_type,
            address.is_primary_address,
        )
        .where(link.link_doctype == "HD Customer")
        .where(link.link_name == customer)
        .where(address.disabled == 0)
        .run(as_dict=True)
    )
    rows.sort(
        key=lambda r: (
            not r.is_primary_address,
            r.address_type != "Billing",
            r.address_title or r.name,
        )
    )
    return [
        {
            "name": r.name,
            "title": r.address_title or r.name,
            "type": r.address_type,
            "is_primary": bool(r.is_primary_address),
            # the project's own customer's address: reading it needs the project, not Address
            "display": render_address(r.name, check_permissions=False) or "",
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


def _detail_values(details: str | dict | None) -> dict:
    """A stage's details from the form: only its known fields, and table rows with only their
    known columns (TBO's Sign-off requirements, Data model)."""
    values = frappe.parse_json(details) if isinstance(details, str) else details or {}
    out = {f: values[f] for f in DETAIL_FIELDS if f in values}
    for field in ("training_date", "trainer"):
        if field in values:
            out[field] = values[field] or None
    for table, columns in DETAIL_TABLES.items():
        if table in values:
            out[table] = [
                {c: row.get(c) for c in columns}
                for row in values.get(table) or []
                if isinstance(row, dict)
            ]
    return out


def _details_of(doc) -> dict:
    """The sign-off's details as the form holds them."""
    return {
        **{f: doc.get(f) for f in DETAIL_FIELDS},
        **{
            table: [{c: row.get(c) for c in columns} for row in doc.get(table)]
            for table, columns in DETAIL_TABLES.items()
        },
    }


def _uat_details(details: str | dict | None, cases: list) -> dict:
    """A UAT's details; its modules start as the SRS's (every module in scope)."""
    values = _detail_values(details)
    if not values.get("modules"):
        values["modules"] = [
            {"module": module, "status": "Completed"}
            for module in dict.fromkeys(
                cstr(c.get("module")) for c in cases if c.get("module")
            )
        ]
    return values


def _project_modules(project: str) -> list[str]:
    """The modules in the project's scope: those its sign-offs have covered, else (a project
    made from a plan) its SRS's."""
    modules = frappe.get_all(
        "HD Signoff Module Item",
        filters={"parenttype": SIGNOFF, "parent": ("in", _signoff_names(project))},
        pluck="module",
        order_by="idx asc",
    )
    if not modules and frappe.db.get_value("Project", project, "custom_crm_plan"):
        try:
            modules = [
                cstr(c.get("module"))
                for c in _uat_cases(project, cached=True).get("cases") or []
            ]
        except frappe.ValidationError:
            frappe.clear_messages()
    return list(dict.fromkeys(m for m in modules if m))


def _signoff_names(project: str) -> list[str]:
    return frappe.get_all(SIGNOFF, filters={"project": project}, pluck="name") or [""]


@frappe.whitelist()
def get_signoff_deliverables(
    project: str, period_from: str, period_to: str, lead: str | None = None
) -> list[dict]:
    """A digital marketing period's deliverables from the content calendar (the requirements:
    "entered or pulled from the delivery report"): per kind of post, how many were planned,
    published, and approved by the client."""
    project = _project_for(project, lead)
    customer = frappe.db.get_value("Project", project, "customer")
    if not customer:
        return []
    posts = frappe.get_all(
        "HD Content Post",
        filters={
            "customer": customer,
            "publish_on": ("between", [period_from, f"{period_to} 23:59:59"]),
            "status": ("!=", "Cancelled"),
        },
        fields=["format", "status", "client_decided_on"],
        limit_page_length=0,
    )
    kinds: dict[str, dict] = {}
    for post in posts:
        kind = _deliverable_kind(post.format)
        row = kinds.setdefault(
            kind,
            {
                "deliverable_type": kind,
                "planned_qty": 0,
                "delivered_qty": 0,
                "approved": 0,
            },
        )
        row["planned_qty"] += 1
        row["delivered_qty"] += post.status == "Published"
        row["approved"] += (
            bool(post.client_decided_on) and post.status != "Changes Requested"
        )
    return [
        {
            "deliverable_type": r["deliverable_type"],
            "planned_qty": r["planned_qty"],
            "delivered_qty": r["delivered_qty"],
            "customer_approved": int(r["approved"] == r["planned_qty"]),
            "link": "",
            "remarks": "",
        }
        for r in kinds.values()
    ]


# a content post type in the words of the requirements' deliverables
DELIVERABLE_WORDS = (
    ("reel", "Reel"),
    ("story", "Story"),
    ("blog", "Blog"),
    ("video", "Video"),
    ("landing", "Landing page"),
    ("ad", "Ad creative"),
)


def _deliverable_kind(post_type: str | None) -> str:
    text = (post_type or "").lower()
    return next((kind for word, kind in DELIVERABLE_WORDS if word in text), "Post")


def _detail_meta() -> dict:
    """Each detail field's label, type and choices, and each table's columns, from the
    doctypes, so the forms build their fields from one place."""

    def describe(df) -> dict:
        return {
            "label": _(df.label),
            "fieldtype": df.fieldtype,
            "options": [o for o in (df.options or "").split("\n") if o]
            if df.fieldtype == "Select"
            else None,
            "description": _(df.description) if df.description else None,
        }

    meta = frappe.get_meta(SIGNOFF)
    out = {}
    for field in (*DETAIL_FIELDS, "training_date", "trainer"):
        out[field] = describe(meta.get_field(field))
    for table, columns in DETAIL_TABLES.items():
        df = meta.get_field(table)
        child = frappe.get_meta(df.options)
        out[table] = {
            **describe(df),
            "columns": {c: describe(child.get_field(c)) for c in columns},
        }
    return out

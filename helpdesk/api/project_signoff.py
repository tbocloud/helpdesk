"""Training and UAT sign-offs on a project (Project -> Sign-off tab) and their templates.

Everyone who can read the project sees its sign-offs. Admins, the project's
managers and lead, and a sign-off's trainer create, send, clarify and reopen.
Templates are managed by project managers. Customers never use these endpoints;
they answer on the token page (helpdesk.api.signoff_portal).
See docs/project-signoff.md.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Count
from frappe.utils import cstr, get_fullname

from helpdesk.helpdesk.doctype.hd_project_signoff.hd_project_signoff import (
    EDITABLE_STATUSES,
    NEEDS_FOLLOW_UP,
    SIGNED,
    UAT,
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
    for s in signoffs:
        s.update(counts.get(s.name, {"total": 0, "done": 0, "follow_up": 0}))
        s.trainer_name = get_fullname(s.trainer) if s.trainer else None
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
def get_signoff_form(project: str) -> dict:
    """What the New sign-off dialog offers: active templates, the team (trainers) and the customer's contacts."""
    project = _check_project(project)
    customer = frappe.db.get_value("Project", project, "customer")
    return {
        "customer": customer,
        "templates": _active_templates(),
        "team": [
            {"user": u, "full_name": get_fullname(u)} for u in get_project_team(project)
        ],
        "contacts": _customer_contacts(customer) if customer else [],
    }


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
) -> dict:
    project = _check_project(project)
    if not can_manage_project(project):
        frappe.throw(
            _("Only the project's manager or lead can add sign-offs."),
            frappe.PermissionError,
        )
    if template and not frappe.db.get_value(TEMPLATE, template, "is_active"):
        frappe.throw(_("Template {0} isn't active.").format(template))
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
        }
    ).insert(ignore_permissions=True)
    return {"name": doc.name}


@frappe.whitelist(methods=["POST"])
def create_uat_signoff(project: str, signatory_contact: str, trainer: str) -> dict:
    """A UAT sign-off for a project made from an implementation plan: a test case for
    each functional requirement of the plan's approved SRS on the ERP site (its module the
    section, its steps and expected result the help text). A draft, edited and sent like
    any sign-off."""
    project = _check_project(project)
    if not can_manage_project(project):
        frappe.throw(
            _("Only the project's manager or lead can add sign-offs."),
            frappe.PermissionError,
        )
    plan = frappe.db.get_value("Project", project, "custom_crm_plan")
    if not plan:
        frappe.throw(_("This project wasn't made from an implementation plan."))
    if not cstr(trainer).strip():
        frappe.throw(_("Pick who tests with the client."))
    found = _erp_call(project, "get_uat_cases", name=plan) or {}
    cases = found.get("cases") or []
    if not cases:
        frappe.throw(_("The plan's SRS has no requirements to test."))
    doc = frappe.get_doc(
        {
            "doctype": SIGNOFF,
            "project": project,
            "signoff_type": UAT,
            "crm_plan": plan,
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
    return {"name": doc.name}


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
) -> dict:
    """Edit the details and questions of a draft or reopened sign-off."""
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
    doc.log_event(_("Edited"))
    doc.save(ignore_permissions=True)
    return {"name": doc.name}


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
) -> dict:
    """Create a template (no `template`) or replace an existing one's details and questions."""
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
        .select(template.name, template.template_name, template.module)
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
        .select(contact.name, contact.full_name, contact.email_id)
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

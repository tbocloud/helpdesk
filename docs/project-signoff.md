# Project sign-off

A **sign-off** is the customer's written acceptance of one stage of a project: a module's
training (Accounts: Sales, Purchase…; HR…), UAT, and (with the templates still to come) the SRS,
go-live, handover or a month of digital marketing. It follows **TBO's Sign-off requirements**
("Sign-off Feature Enhancement – Developer Requirements", 12 Nov 2026), built in three parts:

1. **This part (done):** one dialog to set up, fill in and send a sign-off, **Edit in full page**
   with a mail and a document preview, the customer's name and address fetched, To and CC, the
   mail sent from the app as a Communication, the requirements' statuses with **Mark signed off**
   and **Mark changes requested**, the mail history, the attached sign-off document, and the
   requirements' roles.
2. **Next:** the ERPNext Implementation details (modules table, SRS, environment, UAT and go-live
   dates, support period, open items, data migration), its print format and its six templates.
3. **Then:** the Digital Marketing details (services, platforms, period, deliverables,
   performance, ad spend, carry-forward items), its print format and its four templates.

The sign-off goes to the contact who signs for the customer as a mail from the app, with the
sign-off document attached and, when it has questions, a link to a **questions page** where the
customer answers each item **Done**, **Not clear** or **Escalate** (a UAT: **Pass**, **Fail**,
**Blocker**). Not clear and Escalate become tasks for our people. The customer **accepts by
replying to the mail**; the reply lands in the sign-off's thread and our coordinator marks it
**signed off** (or **changes requested**). Marking it signed off saves the signed PDF on the
project; when every training sign-off of a project is signed off, a project completion letter
is generated.

## Decisions

- **Accepted by reply, recorded by us** (the requirements' flow). There is no signing on the
  customer's page any more: the customer replies, and a manager, the lead or a coordinator marks
  it signed off with the reply as the evidence (`acceptance_reference`), or marks changes
  requested with what they asked for. The questions page stays: the training mail links to it
  ("the existing questions feature").
- **One sign-off per stage or module, several per project.** One late module must not hold the
  others. The project shows the roll-up ("3 of 5 signed off") and gets the completion letter once
  every training sign-off is signed off; a cancelled one doesn't count.
- **The mail is a Communication** on the sign-off (`frappe.core.doctype.communication.email._make`,
  without its "email" permission check, which only System Managers would pass): it shows in the
  mail history and the customer's reply threads onto it when an incoming email account receives
  it. It goes from the sender's own outgoing email account when they have one, else the site's
  default.
- **Snapshot when sent**: the customer's address (`address_display`), the contact's name,
  designation and email are kept as they were, so the mail and the document don't change when
  the customer's records do.
- **Templates are data, not code** (Settings → Sign-off templates). Questions are **copied** into
  a sign-off when it is created (or edited on the full page before saving), so editing a template
  never changes a sign-off already made.
- **Placeholders are filled, never run**: `{{ name }}` is replaced from the sign-off with a
  regular expression, not rendered with Jinja (the requirements say `frappe.render_template`), so
  a template's text can never execute anything. The syntax is the same.
- **Not clear creates a task**, not a ticket: it is project work for the trainer.

## Statuses

| Status | Meaning |
| --- | --- |
| Draft | Made, not sent; details, mail and questions can be edited. |
| Sent | The mail went out. Read-only except the status actions. Reads **Viewed** once the customer opened the questions link with their code since it was sent (`customer_status`). |
| Changes Requested | The customer asked for changes (`remarks`); editable again, and the next send is a new mail in the same thread. The questions link stops until then. |
| Signed Off | The customer accepted; marked by us with the reply. Final: read-only, can't be deleted. |
| Cancelled | Withdrawn by a System Manager, with a reason (`remarks`). |

Statuses are set only by actions; the customer's answers are progress (counts), not a status.
The patch `helpdesk.patches.v16_0_2.signoff_pdf_statuses` maps the earlier statuses: Signed →
Signed Off, Reopened → Changes Requested, Sent / In progress / Needs clarification / Ready to
sign → Sent.

Item answers: **Pending**, **Done**, **Not clear**, **Escalated**.

## Flow

1. **New sign-off** (Project → Sign-off tab → New sign-off / New UAT sign-off; or the lead page,
   [From the lead](#from-the-lead)). The dialog (`SignoffFormDialog.vue`, about 900px, header and
   buttons fixed, the form scrolling) has three sections (`SignoffFields.vue`):
   - **Sign-off setup**: project type (read-only; a select when the project has none, which only
     narrows the templates), sign-off template (filtered by kind and project type, "No template:
     start empty" last; "Mail content and questions are copied in; you can change them before
     sending."), and for a training the module (required only here), training date and trainer;
     a UAT's tester.
   - **Customer**: the customer's name (read-only), its address (read-only, the primary one
     first, **Change** when it has several; "No address on file. Add address", and sending is
     still allowed), who signs (To: a contact of the customer with an email, shown with
     designation and email; the existing "no contacts with an email yet" warning and its link;
     the customer's primary contact is picked when it has an email), and CC (the project lead
     and you; the customer's other contacts are offered; any valid address).
   - **Mail content**: subject and body filled in from the template ([Mail](#mail)), and
     **Attach sign-off document (PDF)**, on by default.
   - Buttons: **Edit in full page** (also an expand icon by the close icon), Cancel, **Save as
     draft**, **Send to customer** (disabled with the reason on hover until it can go; only for
     those who send, [Who can do what](#who-can-do-what)). Send asks once more: "Send sign-off
     mail to Asha Menon <asha@…>? CC: …", and the button is disabled while it goes.
2. **Edit in full page** (`/helpdesk/projects/<project>/signoff/new`, route `TaskySignoffNew`,
   `SignoffEditor.vue`): everything typed in the dialog carries over through the browser
   (`stores/signoffDraft.ts`; no draft record, so an abandoned dialog leaves nothing behind;
   taken once, so a reload starts fresh). Two columns (`SignoffEditorForm.vue`): the fields, a
   tall mail editor and the questions editor (a template's questions, editable before saving; a
   UAT's tests come from the SRS when saved); and a live **Mail preview** (subject, To, CC, the
   body as the customer sees it) and **Document preview** (the sign-off document's HTML,
   `preview_new_signoff_document`), both in sandboxed frames (`SignoffPreview.vue`). Same buttons
   and rules as the dialog, plus Back. Not offered from a lead's page, whose owner may not open
   the project.
3. **An existing sign-off** opens on its own page (`/helpdesk/projects/<project>/signoff/<name>`,
   route `TaskySignoff`, `ProjectSignoff.vue`). Draft or Changes Requested, for those who may edit
   it: the same two-column form (Save changes, Send to customer). Otherwise read-only: details
   (customer, address as sent, To, CC, trainer, the document sent), the signed-off panel, the
   questions with their answers and clarifications, the mail history, the history, and the
   previews of what was sent; and the status actions.
4. **Sending** (`HDProjectSignoff.send_mail`): checks ([Who can do what](#who-can-do-what) and
   [Checks before sending](#checks-before-sending)), keeps the snapshot, makes a new questions
   link when there are questions (the old one stops working), renders the sign-off document and
   saves it on the project (`sent_pdf`) when Attach is ticked, sets Sent, sent on and sent by,
   logs it, and sends the Communication. A send that fails rolls back with the request: it stays
   a draft and the form keeps what was typed.
5. **The customer** reads the mail, opens the questions page if there is one (a code to their
   email, then Done / Not clear / Escalate), and **replies**. Not clear and Escalate need a few
   words, then:
   - a **task** in the project, "Clarify: <question>", for the trainer (the project lead when
     there is none), High priority and due in 3 days (Escalate: Urgent, due tomorrow), with the
     comment and a link back;
   - a notification to the trainer and the project lead; Escalate also to the project's managers
     and Agent Managers, and the team chat channel. Escalating an item with an open task makes it
     Urgent and due tomorrow, and doesn't create a second task.
   When every item is Done the page says "Every item is done. Thank you. Please reply to our
   email to confirm your sign-off."
6. **Mark clarified** (the trainer, the managers, lead and coordinators), with an optional note:
   the item returns to Pending, its task is completed, and the customer is mailed a new link.
   Completing the task elsewhere does the same (`Task.clarify_signoff_item`).
7. **Their reply** (`on_communication_insert`, a Communication hook): written on the history
   ("Reply received") and who sent the mail and the project lead are told.
8. **Mark signed off** (Sent only): the reply (the latest received one by default, or none if it
   came to another mailbox), the date (the reply's by default; never in the future) and who signed
   for the customer (the To contact by default, or another contact of the customer). Then:
   - status Signed Off; signer name, designation, email from the contact; the questions link
     stops;
   - the **signed PDF** (the sign-off document with both signatures: the customer's name,
     designation, date and acceptance reference; ours: the sender's name, designation and date)
     saved on the project, so it shows in the Files tab ([project-files.md](project-files.md));
   - mailed to the signatory, copied to whoever sent it, the trainer and the project lead, in the
     sign-off's thread;
   - who sent it and the project lead are notified; a project made for a lead gets the line on
     the lead's timeline on the ERP site after the commit (`note_signed_on_crm_lead`, as the
     plan's maker, else who sent it; its owner told; a failure is written on the history); a
     UAT's state goes to its plan ([UAT](#uat));
   - when **every** training sign-off of the project (not cancelled) is signed off, the
     **project completion letter** is rendered, saved on the project (`custom_signoff_letter`) and
     mailed to the signatories, trainers and the project lead.
9. **Mark changes requested** (Sent only): what the customer asked for (required). It becomes
   editable; sending it again is a new mail in the same thread ("Mail sent again").
10. **Send reminder** (Sent only): the same mail again with "Reminder:" before the subject and a
    first line "A gentle reminder: we haven't heard from you yet." (with a new questions link when
    there are questions); the status stays Sent. See [Reminders](#reminders).
11. **Cancel** (System Managers only), with a reason: a signed-off training leaves the completion
    letter (the field is cleared); a signed-off UAT's plan on the ERP site hears.
12. **Revoke questions link** (Sent with an open link) and **Delete draft** (drafts only) stay.

### Checks before sending

`check_ready_to_send`, and the same words on the form:
- the project has a customer; who signs is picked and has an email (a contact of the customer);
- CC are valid emails (the signatory is never copied on their own mail);
- subject and body are not empty;
- no placeholder is left unfilled ("Fill Training date: it is used in the mail.");
- a training has its module (and, on the form, its trainer);
- a mail that links to the questions page has questions;
- a missing address only warns.

## Mail

What the customer gets is the sign-off's own mail: subject, body (rich text: bold, italic,
lists, link) and CC, kept on the sign-off (`email_subject`, `email_body`, `cc_emails`).

- **Where it comes from.** A template's mail (Settings → Sign-off templates: Subject, Body, Always
  CC), or, when it has none (or there is no template), the standard mail of its kind
  (`hd_signoff_template.TRAINING_MAIL`, `UAT_MAIL`).
- **Placeholders**: `{{ contact_salutation }}` (the contact's salutation; "Sir/Madam" when it
  isn't known), `{{ contact_name }}`, `{{ customer_name }}`, `{{ customer_address }}` (blank when
  there is none), `{{ project_name }}`, `{{ modules }}` (the module; a UAT's: its tests' sections
  from the SRS), `{{ training_date }}`, `{{ trainer_name }}`, `{{ sign_off_link }}`,
  `{{ sender_name }}`, `{{ sender_designation }}` (the sender's Employee designation, blank when
  unknown), `{{ company_name }}` (the helpdesk's brand name). The ERPNext and Digital Marketing
  placeholders come with parts 2 and 3.
- **Filling in** (`preview_signoff_mail`): when the template is picked, and again whenever a field
  it uses changes, until the mail is changed by hand; then **Reapply template** puts it back after
  asking ("Your changes to the mail are lost").
- **The link** goes where `{{ sign_off_link }}` is, else at the end, with how the one-time code
  works, when the sign-off has questions; without questions no link goes.
- **To** is only the signatory: to send to someone else, add them as a contact of the customer
  first. **CC** starts as the project lead and the person sending, plus the template's Always CC.

## From the lead

The lead page's **Documents** card (`LeadDocuments.vue`) ends with the **UAT sign-off** step of a
project made from an implementation plan. Its status comes from the hub (`get_lead_signoff(lead)`)
in the customer's terms (*Sent*, *Viewed*, *Changes Requested*, *Signed Off*, with who signed off
and a **Signed PDF** link), read again every 30 seconds while the page is in view.

- The card's one button: **Send for sign-off** when the project has no UAT sign-off and the person
  may send one, opening the dialog for a UAT (no Edit in full page from here); **Open sign-off**
  for someone who can open the project; otherwise the status in words.
- **Who**: the lead's owner (not in the requirements' roles; kept from before), and those who send
  sign-offs; anyone who may see the lead sees the status and downloads the signed PDF
  (`download_lead_signoff_pdf`).
- **How the hub knows**: `get_lead` on the ERP site, as the person, says they may see the lead,
  who owns it and which project is its; kept ten minutes per person and lead (`_lead_access`).

## Reminders

Besides **Send reminder** by hand, every day at 10:30 on a working day
(`helpdesk.follow_ups.WorkCalendar`), `send_signoff_reminders` sends **one** reminder for each
sign-off still **Sent** two working days after it went out and not reminded since, in the name of
whoever sent it, who is notified. It is written on the history ("Reminder sent") and in
`reminder_sent_on`; sending the mail again after changes were requested starts a new wait. One
that fails is logged and doesn't stop the others.

## UAT

For a project the hub made from an implementation plan on the ERP site (`custom_crm_plan`, see
[proposals.md](proposals.md)), the Sign-off tab offers **New UAT sign-off**
(`create_uat_signoff`). One doctype (**HD Project Signoff**, `signoff_type` Training or UAT).

- **The tests**: the ERP site's `get_uat_cases` for the plan: a test case for each functional
  requirement of the approved SRS (section = its module, question = "FR-ACC-01: <requirement>",
  help text = its steps and "Expected: <criterion>"), read on behalf of the person who made the
  project from the plan (`custom_crm_acting_user`); without it the hub refuses to ask.
- **Answers**: Pass (Done), Fail (Not clear), Blocker (Escalated); a Fail or Blocker becomes a
  "Fix: <test>" task. *Mark fixed* returns it to the client to test again.
- **Signed off**: marking a UAT signed off queues `record_uat_on_erp` after the commit with the
  ERP site's word "Signed" and who signed off (`record_uat` on the plan, which **starts the
  warranty**); cancelling a signed-off one sends "Reopened" (`HDProjectSignoff.erp_state`). A
  state the ERP site couldn't take is written on the history, and **Record on the ERP site**
  sends it again. A UAT isn't in the completion letter.

## Security

The questions page is `/project-signoff?token=…` (`helpdesk/www/project-signoff.html`,
`helpdesk/www/project_signoff.py`, endpoints in `helpdesk/api/signoff_portal.py`).

- **Link token**: `secrets.token_urlsafe(32)`; only its SHA-256 is stored (`link_token_hash`).
  Expires after 30 days; a new link replaces the hash; Revoke, Mark signed off, Mark changes
  requested and Cancel clear it. The page opens only while the sign-off is Sent. The mail itself
  (with the link) is kept as the Communication, readable by those who may read the sign-off, as
  the email queue kept it before.
- **Email code**: 6 digits, only to the signatory's email, 10 minutes in Redis, compared in
  constant time, at most 5 wrong tries, a new code at most once a minute; rate-limited.
- **Session**: a correct code starts a 2-hour session in Redis behind an HttpOnly, SameSite=Lax
  cookie, bound to the sign-off, the token hash and the signatory's email.
- **Endpoints**: `save_response` only (and the code ones). There is no signing and no download on
  the page any more.
- **What the customer sees** (`customer_view`): module, project, customer, trainer, training date,
  the questions with their answers and comments, the trainer's note, and whether every item is
  done. Never tasks, the history, other sign-offs or internal names.
- The sent and signed documents are private Files on the project; project members open them
  through Frappe's private-file check, people who may see the lead through
  `download_lead_signoff_pdf`. The previews render in sandboxed frames, so a mail's HTML runs
  nothing.

## Where it is in the app

- **Project page → Sign-off tab** (`ProjectSignoffs.vue`): roll-up tiles (Signed off n of m, not
  counting cancelled; items needing clarification; with the customer), **Waiting on** (ours first:
  "Not sent yet", "<contact> asked for changes: edit it and send it again", "2 to clarify for our
  team"; then "With <contact>: waiting for their reply"), the completion letter, a status filter
  (All and the five statuses, with counts) and the list with the requirements' columns: sign-off ·
  template, recipient, status, sent on, signed off on. **New sign-off** and **New UAT sign-off**.
- **New sign-off dialog** and **full page**: see [Flow](#flow). The form's state and rules live in
  `desk/src/pages/tasky/useSignoffForm.ts`, shared by both.
- **A sign-off**: see [Flow](#flow), step 3.
- **Settings → Sign-off templates** (`desk/src/components/Settings/Signoff/`): System Managers
  only.
- **The lead page**: the Documents card's UAT step.
- Status and response labels, tones and icons: `desk/src/pages/tasky/signoffMeta.ts`.

## Who can do what

The requirements' roles; checked in `helpdesk/api/project_signoff.py` (`_can_create`,
`_can_send`, `_can_clarify`, `_is_system_manager`). The doctypes give role access to System
Manager only; everything else goes through these checks.

| Action | Who |
| --- | --- |
| See a project's sign-offs | Anyone who can read the project |
| Create and save a draft, edit a draft | The project's managers (its owner and members with the project role "Project Manager") and lead, its coordinators (project role "Project Coordinator"), its team members (e.g. the trainer), System Managers (admins also as project managers) |
| Send, send reminder, mark signed off, mark changes requested, revoke the link, record on the ERP site | The project's managers and lead, its coordinators, System Managers |
| Mark clarified | The sign-off's trainer, and those who send |
| Cancel | System Managers |
| Manage templates | System Managers |
| Send a UAT from the lead page | The lead's owner, and those who send |
| See the UAT's status and signed PDF on the lead page | Anyone who may see the lead |
| Answer the questions | Only the signatory, through the link and code |

## Data model

- **HD Signoff Template** (named by `template_name`): `module`, `signoff_type` (Training or UAT),
  `project_type` (Project's types, now with **Digital Marketing**; blank: any), `description`,
  `is_active`, `email_subject`, `email_body`, `default_cc`, `items` → **HD Signoff Template Item**
  (`section`, `question`, `help_text`). Stage, declaration text and print format come with parts 2
  and 3.
- **HD Project Signoff** (`SO-.YYYY.-.####`): `project`, `project_name`, `project_type` and
  `customer` (fetched), `module_title` (required for a training), `template`, `signoff_type`,
  `crm_plan`, `crm_recorded`, `status`, `training_date`, `trainer`; the recipient:
  `signatory_contact`, `signatory_name`, `signatory_email`, `signatory_designation` (snapshot),
  `customer_address`, `address_display` (snapshot); the mail: `cc_emails`, `email_subject`,
  `email_body`, `attach_pdf`, `sent_pdf` → File; `items`; the link and sending: `link_token_hash`,
  `link_expires_on`, `link_sent_on` (sent on), `link_sent_by` (sent by), `reminder_sent_on`;
  signed off: `signed_on`, `signer_name`, `signer_designation`, `signer_email`, `signed_off_by` →
  Contact, `acceptance_reference` → Communication, `remarks` (changes requested or cancelled),
  `signed_pdf` → File; `log`. The portal-signature fields (`signer_ip`, `signer_user_agent`,
  `audit_ref`) are gone.
- **HD Project Signoff Item**: `section`, `question`, `help_text`, `response`, `customer_comment`,
  `responded_on`, `clarification_task` → Task, `clarified_on`, `clarified_by`,
  `clarification_note`.
- **HD Project Signoff Log** (the history): `event`, `item`, `detail`, `by_email`, `by_name`, `at`,
  `ip_address`. Written for: Created, Edited, Mail sent / sent again, Reminder sent, Link revoked,
  Code verified, Marked Done / Not clear / Escalated, Comment, Clarified, Reply received, Marked
  signed off, Changes requested, Cancelled, Recorded / Not recorded on the ERP site, Not noted on
  the lead.
- **Project.project_type** gains **Digital Marketing**; **Project.custom_signoff_letter** (Link
  File): the latest completion letter.
- A signed-off sign-off can't be changed or deleted; details, mail and questions can't change
  outside Draft and Changes Requested (`prevent_locked_changes`, `prevent_deleting_signed_off`).

## PDF

`helpdesk/templates/signoff/` (`letter_base.html`, `signoff_letter.html`,
`completion_letter.html`), rendered with `frappe.utils.pdf.get_pdf` (wkhtmltopdf, A4), the
helpdesk's brand as letterhead (HD Settings brand logo inlined). Where wkhtmltopdf isn't installed
the same page is saved as print-ready `.html`. Old WebKit: tables, no flex or grid.

The **sign-off document** (`signoff_letter.html`): header (title, number, date), Customer (name,
address, contact person, designation, email), Project (name, project manager, module, training
date, trainer), the questions with their answers, the declaration, and the customer's and our
signature boxes (empty until signed off). The same page is the attachment when sent, the Document
preview, and (filled in) the signed PDF. The requirements' Frappe print formats come with parts 2
and 3; the project's Company and Letter Head aren't used, as this helpdesk's Project has no
Company.

## Templates shipped

`ensure_default_signoff_templates()` adds, only when missing: **Accounts**, **Stock / Inventory**
and **HR & Payroll** (training, with the Module Training mail) and **UAT Sign-off** and **UAT
Sign-off and Go-Live** (the Avera mail) for ERP Implementation projects. The requirements' other
templates come with parts 2 and 3.

## Not in this change

Parts 2 and 3 above: the ERPNext and Digital Marketing fields, tables and placeholders, the
template's stage and declaration, the two Frappe print formats, and the remaining templates.

## API

`helpdesk/api/project_signoff.py` (desk):

- `get_project_signoffs(project)` → `{signoffs, signed, total, completion_letter, can_create,
  can_create_uat}` (training, not cancelled); each with `template`, `signatory_email`,
  `link_sent_on`, `signed_on`, `remarks`, `customer_status`, `total`, `done`, `follow_up`.
- `get_signoff_form(project, lead?)` → `{project_name, project_type, customer, customer_name,
  addresses (primary first, with how each reads), contacts (with designation, is_primary),
  default_contact, default_cc, templates, team, can_send, can_create_uat, placeholder_labels}`.
- `preview_signoff_mail(project, signoff_type, template?, signatory_contact?, module_title?,
  training_date?, trainer?, lead?, customer_address?)` → `{subject, body, cc, missing}`.
- `preview_new_signoff_document(project, values, lead?)` (POST) and
  `preview_signoff_document(signoff)` → the sign-off document's HTML. Nothing saved.
- `get_template_questions(project, template, lead?)` → the template's questions.
- `get_signoff(signoff)` → the sign-off with address, snapshot, mail, `attach_pdf`, `sent_pdf`,
  `remarks`, signed-off fields, items, history, counts, `customer_status`, `can_edit`,
  `can_send`, `can_clarify`, `can_cancel`.
- `get_signoff_mails(signoff)` → the Communications sent and received, newest first, with
  attachments (View mail history).
- POST: `create_signoff(…, customer_address?, attach_pdf?, items?, send?, lead?)`,
  `create_uat_signoff(…, customer_address?, attach_pdf?, send?, lead?)`, `update_signoff(…,
  customer_address?, attach_pdf?)`, `send_signoff`, `send_signoff_reminder`,
  `mark_signed_off(signoff, acceptance_reference?, signed_on?, signed_off_by?)`,
  `mark_changes_requested(signoff, remarks)`, `cancel_signoff(signoff, reason)`,
  `revoke_signoff_link`, `mark_item_clarified`, `record_uat_again`, `delete_signoff` (drafts),
  `save_signoff_template`.
- `get_signoff_templates()`, `get_signoff_template(template)` (System Managers).
- The lead page: `get_lead_signoff(lead)`, `download_lead_signoff_pdf(lead)`.
- Jobs and hooks: `note_signed_on_crm_lead`, `record_uat_on_erp` (queued),
  `hd_project_signoff.send_signoff_reminders` (cron 10:30),
  `hd_project_signoff.on_communication_insert` (Communication after_insert).

`helpdesk/api/signoff_portal.py` (guest, token + code session): `request_code`, `verify_code`,
`logout`, `save_response`; `page_data(token)` and `customer_view(doc)` for the page.

## Tests

`helpdesk/tests/test_project_signoff.py` (helpers `make_signoff_template`, `make_signoff`,
`open_signoff_link`, `signoff_session`, `fake_request`, `fake_pdf_renderer`,
`make_customer_address`, `receive_signoff_reply` in `helpdesk/test_utils.py`; `hold_commits`;
`frappe.sendmail` and the Communication's `_make` mocked): template copy and seeding, signatory
must be a customer contact, a training needs its module, sent without questions carries no link
(and a link with no questions is refused), token hashed and replaced, the code flow, expired and
revoked links, session bound to its sign-off, customer view hides internals and has no signing,
answers don't change the status, Not clear creates the trainer's task, Escalate is urgent,
rewording a question clears its answer, Mark clarified mails a new link, completing the task
clarifies; sending mails the contact with To / CC / the document and keeps the address snapshot,
then is read-only; no document without Attach; the mail history has the sent and received mails
and the reply is logged and its sender told; Mark signed off saves the PDF with the reply as
evidence and locks (no edits, no deleting), only from Sent and not in the future; changes
requested needs remarks, stops the link and is sent again as a new mail; only a System Manager
cancels and the letter is cleared; the completion letter after the last training; the old
statuses are mapped; who creates and who sends (trainer drafts only, coordinator sends); only
System Managers edit templates; the UAT from the SRS, Pass / Fail, signed off and cancelled
recorded on the ERP site, retried and recorded by hand; the mail fills in (Sir/Madam), holds back
what is missing, comes from the sender; Viewed; one reminder after two working days, a new wait
after changes; signing off notes the lead; the lead page.

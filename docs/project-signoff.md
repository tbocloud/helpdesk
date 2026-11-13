# Project sign-off

A **sign-off** is the customer's written acceptance of one stage of a project: a module's
training (Accounts: Sales, Purchase…; HR…), UAT, and (with the templates still to come) the SRS,
go-live, handover or a month of digital marketing. It follows **TBO's Sign-off requirements**
("Sign-off Feature Enhancement – Developer Requirements", 12 Nov 2026), all seven changes:
the mail template selector by project type, the mail editor filled in from the template,
**Edit in full page**, the customer's name and address fetched, To / CC and **Send to
customer**, the **ERPNext Implementation** and **Digital Marketing** details with their two print
formats and ten stage templates, and status tracking with the mail history.

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
- **The stage decides the details.** A template has a stage (one of the requirements' ten); a
  sign-off copies it, and the stage says which sections its form and document show, what must be
  filled before it is sent, and what the dialog asks for (the rest are on the full page). One
  table of stages (`hd_signoff_template.STAGES`, `SECTIONS`) drives the server checks, the forms
  (sent by `get_signoff_form`) and the documents. The project types are this site's: the
  requirements' "ERPNext Implementation" is **ERP Implementation**.

## Stages and details

The ten stages (`HD Signoff Template.stage`, copied to the sign-off), their project type, the
sections they show (the documents' "Shown for"), what blocks sending until filled, and what the
New sign-off dialog asks:

| Stage | Project type | Sections | Needed to send | In the dialog |
| --- | --- | --- | --- | --- |
| SRS / Requirement Sign-off | ERP Implementation | requirement | SRS version, SRS date | the same |
| Module Training Sign-off | ERP Implementation | modules, training | modules, training date, trainer | the same |
| UAT Sign-off | ERP Implementation | environment, requirement, modules, UAT, open items | modules, UAT site URL | the same |
| UAT Sign-off and Go-Live | ERP Implementation | + go-live, support | modules, UAT site URL, go-live date | modules, go-live date |
| Go-Live Confirmation | ERP Implementation | environment, data migration, go-live, support | go-live date, live site URL, support dates | go-live date, live site URL |
| Project Completion / Handover | ERP Implementation | modules, open items (pending), support | support end date | the same |
| Content Calendar / Strategy Approval | Digital Marketing | engagement, period, next period plan | services, period | the same |
| Monthly Deliverables Sign-off | Digital Marketing | engagement, period, deliverables, performance, ad spend (only with Paid Ads), carry-forward, next period plan, attachments | services, period | the same |
| Campaign Completion Sign-off | Digital Marketing | engagement, period (campaign dates), deliverables, performance, ad spend, attachments | period | services, period |
| Website / Landing Page Go-Live | Digital Marketing | engagement, website | live URL, go-live date | the same |

The fields of each section (`SECTIONS`):
- **environment**: UAT site URL, live site URL, ERPNext version (default "V16");
  **requirement**: SRS document, version, date; **modules**: the Modules covered table (module,
  key processes covered, status Completed / Partially Completed / Deferred, remarks);
  **uat**: UAT start and end date, issues raised, issues resolved; **open items**: issue,
  severity (High / Medium / Low), agreed action, target date ("Known exceptions accepted by the
  customer"); **training**: training date, trainer, attendees (name, designation);
  **migration**: masters migrated, opening balances migrated, remarks; **go-live**: go-live
  date; **support**: support start and end date, support channel (email or helpdesk).
- **engagement**: services (Social Media, SEO, Paid Ads, Content, Website, Email Marketing) and
  platforms (Instagram, Facebook, LinkedIn, YouTube, Google), chosen as chips; the account
  manager on the document is the project lead; **period**: from and to (a month's deliverables
  default to the previous calendar month), with a link to that period's content calendar on the
  document when the customer has posts in it; **deliverables**: type (post, reel, story, blog, ad
  creative, video, landing page), planned and delivered quantity, approved by the customer, link
  or remarks, which **Fill from the content calendar** counts from the customer's content posts
  in the period (`get_signoff_deliverables`); **performance**: reach, impressions, engagement
  rate, followers gained, website visits, leads, a summary; **ad spend**: approved budget, actual
  spend, billed through (the customer's card or TBO); **carry-forward**: item, reason, moved to;
  **next period plan**; **website**: live URL, go-live date, pages delivered; **attachments**:
  the delivery report, which goes with the mail.

Picking a template fills in the stage's defaults: the template's module as the first module
covered (a training), the project's modules (a UAT: those its sign-offs cover, else its SRS's),
"V16" as the ERPNext version, last month for a month's deliverables, and the template's Attach
default. A training's title is its modules; any other sign-off is named after its stage (or its
template), so **Module** is asked only of a sign-off without a stage. Picking a **UAT template**
makes a UAT (Pass / Fail words; recorded on the plan when there is one). Checks on save: known
services and platforms, periods that run forward, counts that aren't negative, no more issues
resolved than raised, blank table rows dropped (`clean_details`). After sending, the details and
tables are read-only like the mail.

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
     narrows the templates), sign-off template (every template of the project's type, "No
     template: start empty" last; "Mail content and questions are copied in; you can change them
     before sending."), and the stage's dialog details ([Stages and details](#stages-and-details):
     e.g. **Modules covered** as a multi-select of ERPNext modules and **Go-live date** for UAT
     Sign-off and Go-Live); a sign-off without a stage asks its module, training date and
     trainer; a UAT from the plan, its tester.
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
   tall mail editor, every section of the stage with its tables (`SignoffDetails.vue`,
   `SignoffDetailField.vue`, `SignoffTable.vue`) and the questions editor (a template's questions, editable before saving; a
   UAT's tests come from the SRS when saved); and a live **Mail preview** (subject, To, CC, the
   body as the customer sees it) and **Document preview** (the stage's print format,
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
   saves it on the project (`sent_pdf`) when Attach is ticked (with the delivery report when the
   stage has one), sets Sent, sent on and sent by,
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
8. **Mark signed off** (Sent only): the reply (the latest received one by default), or without a
   reply in the thread a **signed copy** uploaded instead (kept on the project), the date (the reply's by default; never in the future) and who signed
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
- the stage's details are filled ("Fill Go-live date: the UAT Sign-off and Go-Live needs it.");
  a sign-off without a stage, its module and trainer;
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
  from the SRS), `{{ training_date }}`, `{{ trainer_name }}`, `{{ erpnext_version }}`,
  `{{ uat_site_url }}`, `{{ live_site_url }}`, `{{ uat_start_date }}`, `{{ uat_end_date }}`,
  `{{ go_live_date }}`, `{{ support_start_date }}`, `{{ support_end_date }}`, `{{ srs_version }}`,
  `{{ srs_date }}`, `{{ services }}`, `{{ period_from }}`, `{{ period_to }}`,
  `{{ sign_off_link }}`, `{{ sender_name }}`, `{{ sender_designation }}` (the sender's Employee
  designation, blank when unknown), `{{ company_name }}` (the helpdesk's brand name). A
  placeholder left empty is named by its field's label ("Fill Go-live date: it is used in the
  mail.").
- **Filling in** (`preview_signoff_mail`, with the details): when the template is picked, and
  again whenever a field it uses changes, until the mail is changed by hand; then **Reapply template** puts it back after
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
  `is_active`, `stage` (the ten), `declaration_text` (printed in the document),
  `attach_pdf_default`, `print_format` (→ Print Format; blank: the stage's kind's),
  `email_subject`, `email_body`, `default_cc`, `items` → **HD Signoff Template Item** (`section`,
  `question`, `help_text`; optional).
- **HD Project Signoff** (`SO-.YYYY.-.####`): `project`, `project_name`, `project_type` and
  `customer` (fetched), `module_title` (required for a training), `template`, `signoff_type`,
  `crm_plan`, `crm_recorded`, `status`, `training_date`, `trainer`; the recipient:
  `signatory_contact`, `signatory_name`, `signatory_email`, `signatory_designation` (snapshot),
  `customer_address`, `address_display` (snapshot); the mail: `cc_emails`, `email_subject`,
  `email_body`, `attach_pdf`, `sent_pdf` → File; `items`; the link and sending: `link_token_hash`,
  `link_expires_on`, `link_sent_on` (sent on), `link_sent_by` (sent by), `reminder_sent_on`;
  signed off: `signed_on`, `signer_name`, `signer_designation`, `signer_email`, `signed_off_by` →
  Contact, `acceptance_reference` → Communication, `remarks` (changes requested or cancelled),
  `signed_copy` (Attach, the other acceptance), `signed_pdf` → File; `log`; the stage:
  `stage`, `declaration`, and the details of [Stages and details](#stages-and-details)
  (`erpnext_version`, `uat_site_url`, `live_site_url`, `srs_reference`, `srs_version`,
  `srs_date`, `uat_start_date`, `uat_end_date`, `issues_raised`, `issues_resolved`,
  `go_live_date`, `support_start_date`, `support_end_date`, `support_channel`,
  `masters_migrated`, `opening_balances_migrated`, `migration_remarks`, `services`, `platforms`,
  `period_from`, `period_to`, `pages_delivered`, `reach`, `impressions`, `engagement_rate`,
  `followers_gained`, `website_visits`, `leads`, `performance_summary`, `approved_budget`,
  `actual_spend`, `billed_through`, `next_period_plan`, `delivery_report`) with the child tables
  **HD Signoff Module Item** (`modules`), **HD Signoff Open Item** (`open_items`), **HD Signoff
  Attendee** (`attendees`), **HD Signoff Deliverable** (`deliverables`) and **HD Signoff Carry
  Forward Item** (`carry_forward`). The portal-signature fields (`signer_ip`, `signer_user_agent`,
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

Two print formats, as the requirements ask: **Sign-off – ERPNext Implementation** and **Sign-off –
Digital Marketing** (standard Print Formats of the app, `helpdesk/helpdesk/print_format/`), whose
Jinja includes the app's templates `helpdesk/templates/signoff/signoff_erpnext.html` and
`signoff_digital.html` (sharing `signoff_parts.html` and `letter_base.html`). A sign-off uses its
template's print format, else its kind's (`document_source`); opened from Frappe's print view,
the format computes its own context (`document_context`). Each section shows only for the stages
listed against it; the document is titled after the stage ("UAT Sign-off and Go-Live
Certificate"), numbered `SO-.YYYY.-.####` and dated, on **our letterhead**: the site's default
Letter Head when there is one, else the helpdesk's brand (this Project has no Company). Sections:
Header, Customer (name, address, contact, designation, email), Project (name, ERPNext version,
project manager, project coordinator) or Engagement (services, platforms, account manager), the
stage's sections, the questions with their answers when there are any, the Declaration (the
template's), and the signatures (the customer's name, designation, date and acceptance reference:
the reply's date or "Signed copy"; ours: name, designation, date).

It is rendered with `frappe.utils.pdf.get_pdf` (wkhtmltopdf, A4); where wkhtmltopdf isn't
installed the same page is saved as print-ready `.html`. The same page is the attachment when
sent, the Document preview and (filled in) the signed PDF. The completion letter is
`completion_letter.html`. Old WebKit: tables, no flex or grid.

## Templates shipped

`ensure_default_signoff_templates()` (install, and the patch
`helpdesk.patches.v16_0_2.signoff_stage_templates`) adds, only when missing, the requirements'
ten, each with its stage, project type, mail, declaration and print format: SRS / Requirement
Sign-off, Module Training Sign-off, UAT Sign-off, UAT Sign-off and Go-Live (the Avera mail), Go-Live
Confirmation, Project Completion / Handover, Content Calendar / Strategy Approval, Monthly
Deliverables Sign-off, Campaign Completion Sign-off, Website / Landing Page Go-Live. The mails of
the requirements are used as written; the other five follow their tone (the requirements leave
their final wording to the project coordinator, who can change them in Settings). The training
question sets **Accounts**, **Stock / Inventory** and **HR & Payroll** stay, now with the Module
Training stage. The patch also gives the templates a site already has their stage, declaration
and print format, and replaces an earlier seeded mail (which asked the customer to sign on the
page) with the requirements' mail; a mail a site changed is left alone.

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
- `get_signoff_deliverables(project, period_from, period_to, lead?)` → a period's deliverables
  counted from the customer's content posts.
- `get_signoff_form` also sends `stages`, `sections`, `services`, `platforms`,
  `erpnext_modules`, `project_modules`, `detail_labels` and `fields` (each detail's label, type,
  choices and table columns, from the doctypes).
- `get_signoff(signoff)` → the sign-off with its stage, details (`details`, `shown_sections`),
  address, snapshot, mail, `attach_pdf`, `sent_pdf`, `remarks`, signed-off fields, items, history, counts, `customer_status`, `can_edit`,
  `can_send`, `can_clarify`, `can_cancel`.
- `get_signoff_mails(signoff)` → the Communications sent and received, newest first, with
  attachments (View mail history).
- POST: `create_signoff(…, customer_address?, attach_pdf?, items?, details?, send?, lead?)`,
  `create_uat_signoff(…, customer_address?, attach_pdf?, details?, send?, lead?)`,
  `update_signoff(…, customer_address?, attach_pdf?, details?)`, `send_signoff`,
  `send_signoff_reminder`,
  `mark_signed_off(signoff, acceptance_reference?, signed_on?, signed_off_by?, signed_copy?)`,
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
after changes; signing off notes the lead; the lead page; the ten templates seeded with their
stage; a stage's details block sending until filled; a training is named after its modules; a
month's deliverables default to last month and show ad spend only with Paid Ads (and unknown
services are refused); each kind gets its document with its sections; the go-live details fill
the mail; only trainings count for the completion letter; a UAT template makes a UAT; a signed
copy is accepted as the evidence.

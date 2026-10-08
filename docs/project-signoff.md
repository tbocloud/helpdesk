# Project sign-off

After each project, TBO trains the customer module by module (Accounts: Sales, Purchase…;
HR…). A **sign-off** is the customer's written confirmation that one module's training is
complete. The customer gets a web page with that module's checklist and answers each item
**Done**, **Not clear** or **Escalate**. Not clear and Escalate go to our people as tasks;
once they have explained, the item goes back to the customer. When every item is Done the
customer signs, a PDF is saved on the project, and when every module of the project is signed
a project completion letter is generated.

## Decisions

- **One sign-off per module / training, several per project.** Trainings happen on different
  days with different trainers and often different people on the customer's side, and one
  late module must not hold the others' signatures. The project shows the roll-up ("3 of 5
  signed") and gets the **project completion letter** once every sign-off is signed.
- **Signature = typed full name + designation + a confirmation tick.** No drawn signature.
  The audit trail records the signer's email, name, designation, time, IP address and user
  agent, and a SHA-256 **audit reference** of the signed questions and answers, printed on
  the PDF.
- **Customer access = secure link + email code.** See [Security](#security).
- **Templates are data, not code** (Settings → Sign-off templates). Questions are **copied**
  into a sign-off when it is created, so editing a template never changes a sign-off already
  sent, and a sign-off's questions can be changed while it is a draft (or reopened).
- **Not clear creates a task**, not a ticket: it is project work for the trainer, and tasks
  already have assignees, due dates, notifications and the meeting card (schedule a session
  with the customer from the task). No new meeting UI.

## Statuses

| Status | Meaning |
| --- | --- |
| Draft | Created; questions can be edited; the customer hasn't seen it. |
| Sent | The link went out; nothing answered yet (also after an item returns from clarification and nothing else is answered). |
| In progress | Some items answered, none waiting on us. |
| Needs clarification | At least one item is Not clear or Escalated. |
| Ready to sign | Every item is Done. |
| Signed | Signed by the named signatory; locked. |
| Reopened | A signed sign-off was reopened with a reason; questions can be edited again and a new link sent. The next answer moves it on like any other. |

Draft, Signed and Reopened are set by actions; the others follow the answers
(`HDProjectSignoff.refresh_status`).

Item responses: **Pending**, **Done**, **Not clear**, **Escalated**.

## Flow

1. **Create** (Project → Sign-off → New sign-off; project managers, the project lead,
   admins): template (or empty), module title, training date, trainer (from the project
   team), and who signs for the customer (a contact of the project's customer, with an
   email). A project without a customer can't have sign-offs. A sign-off made without a
   template starts with no questions; it saves as a draft but can't be sent until it has
   at least one.
2. **Edit** (Draft or Reopened): details and questions (add, remove, reorder, reword). A
   reworded question is treated as new: its answer, comment, answer time, clarification
   task and clarification details are cleared and it goes back to Pending.
3. **Send to customer**: a new link is emailed to the signatory. **Resend** sends a new link
   and the old one stops working. **Revoke** stops the link at once.
4. **Customer**: opens the link, asks for a code, enters it, and answers. Done saves at once.
   Not clear and Escalate need a few words ("what needs explaining"), then:
   - a **task** in the project, "Clarify: <question>", assigned to the trainer (the project
     lead when there is no trainer), High priority and due in 3 days (Escalate: Urgent, due
     tomorrow), with the customer's comment and a link back to the sign-off;
   - a notification (bell, plus email or Teams per HD Notification) to the trainer and the
     project lead; Escalate also to the project's managers (owner and members with the
     "Project Manager" project role) and Agent Managers, and to the team chat channel.
   Changing Not clear to Escalated on an item with an open task makes that task Urgent,
   brings its due date forward to tomorrow when it was later, and notifies the managers; it
   doesn't create a second task.
   Done items can carry an optional comment (saved when the box loses focus).
5. **Mark clarified** (the trainer, the lead, managers, admins), with an optional note shown
   to the customer: the item returns to **Pending**, its task is completed, and the
   customer is emailed "1 item is ready for you to review again" with a **new link** (the
   only way to put a working link in the email, since the token is stored hashed). Completing
   the clarification task anywhere else (My Work, the board) does the same, without a note
   (`Task.clarify_signoff_item`).
6. **Sign**: only when every item is Done, by the signatory's verified session, with full
   name, designation and the tick "I confirm that the training listed above has been
   completed to our satisfaction". Signing:
   - records signer name, designation, email, time, IP, user agent and the audit reference;
   - renders the **signed PDF** and saves it as a private File on the Project, so it shows in
     the project's Files tab ([project-files.md](project-files.md));
   - emails the PDF to the signatory, the trainer and the project lead;
   - checks the project: when **every** sign-off of the project is Signed, renders the
     **project completion letter** (every module with its training date, trainer, signer and
     audit reference), saves it on the project (Project `custom_signoff_letter`) and emails
     it to the signatories, trainers and the project lead.
7. **Reopen** (Signed only; reason required): the reason, the previous signer and the old PDF
   are written to the history; signature fields are cleared; the signed PDF stays on the
   project; the project's completion letter field is cleared. Signing again generates a new
   PDF (and a new completion letter once all are signed).

## Security

The customer page is `/project-signoff?token=…` (`helpdesk/www/project-signoff.html`,
`helpdesk/www/project_signoff.py`), server-rendered like the content portal and sharing its
base template and helpers (`helpdesk/templates/portal_base.html`). Its endpoints are in
`helpdesk/api/signoff_portal.py`.

- **Link token**: `secrets.token_urlsafe(32)` (256 bits). Only its SHA-256 is stored
  (`link_token_hash`); the token itself is only in the email. Expires after 30 days. Sending
  a new link replaces the hash, so earlier links stop working; Revoke clears it. The page
  sets `<meta name="referrer" content="no-referrer">` so the token never leaks to another
  site. An unknown, replaced or revoked token gets the same "isn't valid" answer.
- **Email code**: 6 digits from `secrets`, sent only to the sign-off's signatory email, kept
  in Redis for 10 minutes (stored only after the email is handed over, so a failed send
  leaves no code and no resend wait), compared in constant time, at most 5 wrong tries (then a new code
  is needed), and a new code at most once a minute. `request_code` is rate-limited to 5 an
  hour and `verify_code` to 15 per 10 minutes, per IP and token.
- **Session**: a correct code starts a session in Redis (2 hours) behind an HttpOnly,
  SameSite=Lax (Secure on https) browser-session cookie. The session holds the sign-off, the
  token hash and the signatory email, and every call checks all three against the sign-off
  the token opens: a session can't be used for another sign-off, a new link ends sessions
  opened with the old one, and a changed signatory can't be signed by the old one.
- **Every endpoint** (`save_response`, `sign`, `download_pdf`) checks the token and the
  session again; there is no endpoint that takes a sign-off name. Responses are rate-limited
  (300 per 10 minutes) and signing (10 per 10 minutes).
- **Only the signatory signs**: `sign` refuses any session email but the sign-off's
  signatory email.
- **What the customer sees** (`customer_view`): module, project, customer, trainer, training
  date, the questions with their own answers and comments, and the trainer's clarification
  note. Never tasks, the history, other sign-offs, IP addresses or internal names.
- The signed PDF is a private File; the customer downloads it only through
  `download_pdf` with a valid session. Project members open it through Frappe's private-file
  check (read on the Project).

## Where it is in the app

- **Project page → Sign-off tab** (`/helpdesk/projects/<project>/signoff`, route
  `TaskySignoffs`, `desk/src/pages/tasky/ProjectSignoffs.vue`): roll-up tiles (Signed n of m,
  items needing clarification, sign-offs with the customer), the completion letter when every
  sign-off is signed, and the list (module, status badge, signatory, trainer, training date,
  items to clarify, done/total). **New sign-off** (`components/SignoffFormDialog.vue`).
- **A sign-off** (`/helpdesk/projects/<project>/signoff/<name>`, route `TaskySignoff`,
  `ProjectSignoff.vue`): status, signatory, trainer, training date, template, link status;
  actions by state (Edit and Send to customer for drafts; Resend link; Revoke link; Signed
  PDF; Reopen; Delete draft); counts; signature panel; the questions by section with each
  answer, the customer's comment, the clarification (who, when, note), the task (opens the
  task panel, with its meetings) and **Mark clarified**; the history.
- **Settings → Sign-off templates** (`desk/src/components/Settings/Signoff/`): list (inactive
  greyed, question count) and an editor (name, module, description, Active, questions). The
  question editor (`desk/src/components/SignoffQuestionsEditor.vue`) is shared with editing a
  sign-off.
- Status and response labels, tones and icons: `desk/src/pages/tasky/signoffMeta.ts`.

## Who can do what

| Action | Who |
| --- | --- |
| See a project's sign-offs | Anyone who can read the project (`frappe.has_permission("Project", "read")`) |
| Create | Admins, the project's managers, the project lead (`can_manage_project`) |
| Edit, send, resend, revoke, mark clarified, reopen, delete a draft | The above, plus the sign-off's trainer |
| Manage templates | Project managers (includes admins: `is_project_manager`) |
| Answer and sign | Only the signatory, through the link and code |

The doctypes give role access to System Manager only; everything else goes through these
checks in `helpdesk/api/project_signoff.py`.

## Data model

- **HD Signoff Template** (named by `template_name`): `module` (suggested module title),
  `description`, `is_active`, `items` → **HD Signoff Template Item** (`section`, `question`,
  `help_text`; order is `idx`).
- **HD Project Signoff** (`SO-#####`): `project`, `project_name` and `customer` (fetched),
  `module_title`, `template`, `status`, `training_date`, `trainer`, `signatory_contact`
  (Contact of the customer; `signatory_name` and `signatory_email` come from it), `items`,
  link (`link_token_hash`, `link_expires_on`, `link_sent_on`, `link_sent_by`), signature
  (`signed_on`, `signer_name`, `signer_designation`, `signer_email`, `signer_ip`,
  `signer_user_agent`, `audit_ref`, `signed_pdf` → File), `log`.
- **HD Project Signoff Item**: `section`, `question`, `help_text`, `response`,
  `customer_comment`, `responded_on`, `clarification_task` → Task, `clarified_on`,
  `clarified_by`, `clarification_note`.
- **HD Project Signoff Log** (the history): `event`, `item` (row name), `detail`, `by_email`,
  `by_name`, `at`, `ip_address`. Written for: Created, Edited, Link sent / resent, Link
  revoked, Code verified, Marked Done / Not clear / Escalated, Comment, Clarified, Signed,
  Reopened. Kept on the document (not Version), so it is complete in tests and readable by
  the API.
- **Project.custom_signoff_letter** (custom field, Link File, read only): the latest
  completion letter, cleared on reopen.
- The signatory is checked against the customer's contacts when set or changed, so a
  contact later removed from the customer doesn't block a sign-off already under way.
- A signed sign-off can't be saved except by its own actions (reopen); questions can't be
  changed outside Draft and Reopened (`prevent_locked_changes`).

## PDF

`helpdesk/templates/signoff/` (`letter_base.html`, `signoff_letter.html`,
`completion_letter.html`), rendered with `frappe.utils.pdf.get_pdf` (wkhtmltopdf, A4). The
letterhead is the helpdesk's brand (HD Settings brand logo, inlined as a data URI so the
renderer never fetches it, else the brand name). Where wkhtmltopdf isn't installed the same
page is saved as a print-ready `.html` file instead, as the content delivery report does.
Old WebKit: tables, no flex or grid.

## Templates shipped

`ensure_default_signoff_templates()` (install and patch
`helpdesk.patches.v16_0_2.seed_signoff_templates`) adds, only when a template of that name is
missing: **Accounts** (Sales, Purchase, Payments, Reports), **Stock / Inventory** (Items and
warehouses, Stock movements, Receipts and deliveries, Stock reports) and **HR & Payroll**
(Employees, Attendance and leave, Payroll), written as things the customer can now do.

## API

`helpdesk/api/project_signoff.py` (desk):

- `get_project_signoffs(project)` → `{signoffs, signed, total, completion_letter, can_create}`;
  each sign-off has `total`, `done`, `follow_up`.
- `get_signoff_form(project)` → `{customer, templates, team, contacts}`.
- `get_signoff(signoff)` → the sign-off with items, history (newest first), counts,
  `link_open`, `can_manage`, `can_edit`.
- POST: `create_signoff`, `update_signoff`, `send_signoff_link`, `revoke_signoff_link`,
  `mark_item_clarified(signoff, item, note)`, `reopen_signoff(signoff, reason)`,
  `delete_signoff` (drafts only), `save_signoff_template`.
- `get_signoff_templates()`, `get_signoff_template(template)`.

`helpdesk/api/signoff_portal.py` (guest, token + code session): `request_code`,
`verify_code`, `logout`, `save_response`, `sign`, `download_pdf`; `page_data(token)` and
`customer_view(doc)` for the page.

## Tests

`helpdesk/tests/test_project_signoff.py` (helpers `make_signoff_template`, `make_signoff`,
`open_signoff_link`, `signoff_session`, `fake_request`, `fake_pdf_renderer` in
`helpdesk/test_utils.py`; `hold_commits`; `frappe.sendmail` mocked): template copy and
seeding, an empty draft saves but can't be sent, rewording a question clears its answer,
signatory must be a customer contact, token hashed and replaced, code flow (wrong
code, used once, attempts limit, expiry), expired and revoked links, session bound to its
sign-off, token and email, customer view hides internals, Not clear creates the trainer's
task and notifies, Escalate is urgent and reaches managers, escalating an open task makes
it urgent and due tomorrow, Mark clarified returns the item
and emails a new link, completing the task clarifies, signing needs all Done and the
signatory, signing saves the PDF on the project and locks, reopen needs a reason and is
logged, the completion letter once every sign-off is signed, and permissions (members view,
only managers, the lead or the trainer act, outsiders refused; only project managers edit
templates).

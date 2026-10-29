# Client credentials

The logins a Digital Marketing client hands over so the team can post for them, and the
hand-back when the client leaves. It sits on the project: the **Credentials** tab
(`/projects/:id/credentials`, `ProjectCredentials.vue`).

## The flow

Lead → 6-month strategy proposal → client accepts → **credentials handover** → content calendar
(each post red until the client approves, green after) → project and team. If the client
cancels (say after three months): **Hand back & close** returns the credentials with the
client's sign-off, then closes the project.

## Data

- **HD Client Credential Handover**: `project`, `direction` (Received from client / Returned to
  client), `handed_over_on`, `handed_over_by` (the person at the client), `received_by` (our
  user), `items`, and for a hand-back `client_signoff_name`, `signed_on`, `close_reason`;
  `remarks`. Named `CH-#####`. Permissions: System Manager only.
- **HD Client Credential** (child): `platform` (Facebook, Instagram, LinkedIn, YouTube, X,
  Google Business, Website / CMS, Meta Business Suite, Google Ads, Other), `account_url`,
  `username`, `password` (Password field, encrypted in `__Auth`), `two_factor_contact`, `notes`,
  `returned_from` (on a hand-back row, the received row it returns).

The owner hasn't sent the client's form yet, so these fields are a default. To change them,
edit the child doctype's JSON, `CredentialsFormDialog.vue` and `format_handover`; the platform
list is the doctype's Select, read by the API and the form.

## Who may

`can_handle_credentials(project)` in `helpdesk/tasky/permissions.py`: System Manager and
Administrator, the project's managers (its owner or a member with the Project Manager project
role), its lead, and the heads of its department (`department_heads`: the Digital Marketing
Head for Digital). Not project members or coordinators, not Agent Managers, and never a Sales
Employee. `get_project_detail` carries `can_handle_credentials`, which shows the tab. Every
endpoint checks it, then works as the system (the doctypes allow nobody else).

## API (`helpdesk/api/client_credentials.py`)

| Method | What it does |
| --- | --- |
| `get_credentials(project)` | The handovers, newest first, and the project status. Each login has `has_password`, **never** the password |
| `save_handover(project, handed_over_by, items, handed_over_on, remarks, name)` | A new Received handover, or a change to one. A login sent with its `name` keeps its password unless a new one is sent; a login left out is removed with its password. A hand-back can't be changed |
| `reveal_password(project, handover, item)` | One password, and a Comment on the project: "<user> viewed the <platform> password". The page hides it again after 30 seconds |
| `hand_back_and_close(project, client_signoff_name, signed_on, reason)` | See below |

## Hand back & close

`hand_back_and_close` inserts a **Returned to client** handover. Its `before_insert` lists every
credential the project received, **by reference** (`returned_from`; the passwords are not
copied), validation needs the client's name, the date (not in the future) and the reason, and
`after_insert` writes a timeline line and sets the project to **Cancelled** (one save) with the
reason as a comment. A project that is already Completed or Cancelled is refused. Cancelled is
how a lost client is closed; Completed stays for finished work.

## Decisions and open points

- The stored passwords are kept after a hand-back (the record shows what was returned). Wiping
  them on sign-off is a possible next step; ask the owner.
- Open tasks stay as they are when the project is cancelled.
- The project's `custom_crm_proposal` field and the strategy-proposal project are in
  [leads.md](leads.md#content-and-digital-marketing-leads).

## Tests

`helpdesk/tests/test_client_credentials.py`: manager, department head and System Manager may
open; a member and a Sales Employee may not; no password in a list; reveal returns it and
logs; an edit without a password keeps it; the hand-back lists by reference and cancels the
project, once; `create_project_from_proposal` with the ERP mocked (once, Digital, Content
Calendar, linked back).

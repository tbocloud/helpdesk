# Project access and handover

Asked by the owner on 2026-11-28: when someone leaves, the team must still know, without
calling the client, where each project's code lives, which backend and frontend URLs and
apps it runs on, the live and demo logins, and the notes that go with them; and the leaving
person's work must pass to someone else in one place.

Two parts:

1. **Access tab** on every project (`/projects/:id/access`, `ProjectAccess.vue`): a register
   of what the project runs on.
2. **Handover page** (`/handover`, Work → Team → Handover, `EmployeeHandover.vue`): hand a
   leaving person's projects and tasks to others.

The DM clients' social-media logins stay on the Credentials tab
([client-credentials.md](client-credentials.md)); the Access tab is for the technical side of
any project.

## Access tab

### Data: `HD Project Access`

One row per thing: `project`, `kind` (Git repository, Backend / ERP site, Frontend /
website, Mobile app, Server / hosting, Database, API / integration, Login, Other),
`environment` (Live, Staging, Demo, Development), `label` (its name, required), `url`,
`username`, `password` (Password field, encrypted), `notes`, `added_by`. Named by hash,
changes tracked. Permissions: System Manager only; the API checks the rules below and then
works as the system.

### Who may

- **See** the tab (links, usernames, notes, who added each entry):
  `can_see_project_access` = anyone who may read the project (`project_has_permission`
  read). Never a Sales Employee, even when listed on the project.
- **Add, change, remove, and show passwords**: `can_handle_project_access` = the people
  who handle client credentials (`can_handle_credentials`: System Managers, the project's
  managers and lead, its department heads) **plus members with the Developer or DevOps
  Engineer project role** (`DEVELOPER_PROJECT_ROLES`). The owner chose this on 2026-11-28
  ("managers + project developers"); DevOps Engineer was added because servers are theirs.
- Coordinators, designers, content people and other members see the tab without passwords.

`get_project_detail` carries `can_see_project_access`, which shows the tab.

### API (`helpdesk/api/project_access.py`)

| Method | What it does |
| --- | --- |
| `get_project_access(project)` | Entries sorted by kind, with `has_password` and **never** the password; the kinds and environments (from the doctype's Selects); `can_handle` |
| `save_access_entry(project, entry, name)` | Add, or change one. A password changes only when a new one is sent; `clear_password` removes it. Needs a name and a known kind |
| `delete_access_entry(project, name)` | Removes it; the project's timeline says who did |
| `reveal_access_password(project, name)` | One password, and a timeline line "<user> viewed the password of <name>". The page hides it again after 30 seconds |

User-typed names are HTML-escaped in timeline lines.

### Page

One card per kind, each entry with its environment, URL (a link only for http/https),
username and password, each with a Copy button; notes; "Added by". Show/Hide for the
password, Edit and Remove (with a confirm) only for `can_handle`. Empty state explains what to
add.

## Handover

### Data: `HD Employee Handover` (+ child `HD Employee Handover Project`)

`employee`, `last_day`, `status` (Draft, Done), `default_owner` (takes their tasks outside
projects), `other_tasks_moved`, `completed_by`, `completed_on`, `note`, and `projects`: one
row per project with `project`, `project_role` (theirs), `new_owner`, `note`, `tasks_moved`.
Named `EH-#####`. System Manager only, like the access entries.

### Who may

`can_hand_over`: admins (System Manager, Agent Manager), holders of the Project Manager
role, and department heads. The menu item and the route follow `can_hand_over` (sent at
sign-in).

### What completing does (`HDEmployeeHandover.complete`)

For each project row:

1. Each **open** task (not Completed, Cancelled or Template) where the leaver is an assignee
   is given to the new owner through the usual reassign (`tasky.api._reassign`); other
   assignees keep their share. Closed tasks are left as they were. The new owner gets one
   notice per project.
2. The new owner joins the team with the leaver's project role (if not already on it), the
   leaver leaves the team, and if the leaver was the project lead the new owner becomes lead.
   One save per project.
3. The project's timeline says who left, who took it over, how many tasks moved, and the note.

Then their open tasks outside any project go to `default_owner`, and the handover is marked
Done. A handover can't be completed twice; the leaver can't take over their own work; a
project they aren't on (or that is closed) is refused.

The access entries the leaver added stay on their projects; the page shows how many per
project so the new owner can check them.

### API (`helpdesk/api/employee_handover.py`)

| Method | What it does |
| --- | --- |
| `get_people()` | `people`: everyone still holding an open project or open task, disabled accounts included; `takers`: the active agents |
| `get_handover_preview(employee)` | Their open projects with role, lead or not, open tasks, access entries they added and a suggested new owner (the lead, else a project manager, never the leaver); tasks outside projects; past handovers |
| `complete_handover(employee, projects, default_owner, last_day, note)` | Records and completes it |

### Decisions and open points

- The leaver's account is not disabled here; offboarding (`helpdesk.offboarding`) does that.
- Tickets assigned to the leaver are not moved yet.
- Not yet shown on the person's page; only on the Handover page.

## Tests

`helpdesk/tests/test_project_access.py`: the team sees links but no password; outsiders and
Sales Employees see nothing; developers and managers reveal and it is logged; other members
can't reveal or change; an edit without a password keeps it, `clear_password` removes it;
name and kind are required; removing is logged.

`helpdesk/tests/test_employee_handover.py`: the preview; completing moves open tasks (not
closed ones, not other assignees'), the team place, the role and the lead, logs the note,
moves tasks outside projects, and marks it done; only managers and heads may; the leaver
can't take their own work; a project they aren't on is refused.

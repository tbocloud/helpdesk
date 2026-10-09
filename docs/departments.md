# Departments and creative roles

TBO is organised in five departments: **ERP**, **Digital**, **Creative**, **GrowthX** and
**Internal / R&D**. Every project can belong to one, and the Projects page groups projects by
department. Project members can also hold creative and digital roles, and template tasks in
the matching categories go to them.

## Where it is in the app

- **Settings → Departments** (System Managers and Agent Managers): the list in display order.
  Add a department, rename it (its projects move with it), move it up or down, deactivate or
  activate it, or delete it. A department that projects still use can't be deleted; the
  message says how many projects use it and suggests moving them or deactivating it instead.
- **New / Edit project** dialog: a **Department** picker listing active departments in order.
  A project already in an inactive department keeps it, shown as "(inactive)". A new project
  starts in the department the Projects page is filtered to.
- **Projects page**: the status tabs and search stay. Below them, department chips (All
  departments, each department, No department) show one department alone. Projects are
  listed in one section per department (name and project count), in department order, then a
  **No department** section last. Departments with no matching projects are hidden. The
  status-tab counts follow the department filter, and each chip counts projects in the
  current status tab. The filter is kept in the URL as `department` (`__none__` for No
  department), with the page's other filters (see [workspace-pages.md](workspace-pages.md)).
- **Overview**: a **Department** filter next to Project, Customer and Assignee (kept in the
  URL like the others). It narrows the page to tasks of that department's projects; tickets
  are left out, as with the Project filter, because tickets belong to customers, not
  departments. It combines with the other filters (e.g. a customer's projects in one
  department). API: `helpdesk.api.work.get_overview(department=...)`.

## Department walls: DM Employee and ERP Employee

Two roles (created on install and migrate by `content_team.ensure_role()`, given to agents) keep
each team out of the other's department:

| Role | Never sees |
| --- | --- |
| **DM Employee** | the **ERP** department |
| **ERP Employee** | the **Digital** department, the content calendar and the work Calendar |

Creative, GrowthX, Internal / R&D and projects with no department stay visible to both. System
Managers and Agent Managers see every department.

- **What's hidden** (`hidden_departments()` in `helpdesk/tasky/permissions.py`, mapping
  `HIDDEN_DEPARTMENTS`): that department's projects and their tasks, in every list
  (`project_query`, `task_query`: Projects, My Work, Overview, Calendar, Desk) and when opened
  directly (`project_has_permission`, `task_has_permission`), and its chip in the department
  filters (`get_departments`).
- **No assignments across the wall:** a ToDo `validate` hook (`check_assignment_department`)
  refuses giving a task in a hidden department to that person ("… can't be given tasks in the ERP
  department."), from any screen, the Desk or templates. This is needed because Frappe shares a
  task with its assignee, and a share would let them open it even though it's hidden from their
  lists.
- **Content calendar for ERP Employees** (`content_team.is_erp_only()`, unless they also edit
  content): HD Content Post `permission_query` returns no posts and `has_permission` refuses
  them; the sidebar hides Content and Calendar, and the router sends `ContentCalendar`,
  `ContentReport`, `ContentPlans` and `WorkCalendar` to Home (`ERP_EMPLOYEE_HIDDEN_ROUTES` in
  `pages/content/contentTeam.ts`, `authStore.isErpOnly`).
- **Support pages hidden from both** (`content_team.is_department_employee()`, false for System
  Managers and Agent Managers; `authStore.isDepartmentEmployee`): Support hours, Tickets,
  Customers, Contacts, Templates, Knowledge base and Customer report leave the sidebar, and their
  routes (`DEPARTMENT_EMPLOYEE_HIDDEN_ROUTES` in `pages/content/contentTeam.ts`, including single
  tickets, customers, contacts and articles) send them to Home; the command palette drops
  Knowledge Base. Tickets are also hidden on the server: `sees_no_tickets()` gives them the same
  ticket visibility as the Content Team (only tickets they raised themselves).
- The walls go by department **name** ("ERP", "Digital"). Renaming either department in
  Settings → Departments turns its wall off until `HIDDEN_DEPARTMENTS` is updated. Projects with
  no department aren't walled, so set each project's department for the walls to apply.

## Data model

- **HD Department** (`helpdesk/helpdesk/doctype/hd_department`): `department_name` (Data,
  unique, also the record name via `field:department_name`, renamable), `sort_order` (Int, new
  departments go to the end), `is_active` (Check, default 1), `description`. System Manager
  and Agent Manager have full access; Agent and Project Manager can read.
- **Project.custom_department**: Link → HD Department, defined in
  `helpdesk/setup/install.py` `get_custom_fields()` and applied on install and on every
  migrate. It is a standard filter.
- **Seeding**: `ensure_default_departments()` (in `hd_department.py`) inserts any of the five
  defaults that are missing and leaves existing, renamed or deactivated ones alone. It runs from
  `after_install` and from the patch `helpdesk.patches.v16_0_2.seed_departments` for existing
  sites. Patches run once, so a default deleted later stays deleted.

## API

`helpdesk/api/departments.py`:

| Method | HTTP | Permission | What it does |
| --- | --- | --- | --- |
| `get_departments(include_inactive=False)` | GET | read | Departments in order, each with `project_count` |
| `add_department(department_name, description=None)` | POST | create | Adds one at the end |
| `rename_department(department, new_name)` | POST | write | `frappe.rename_doc`; projects follow |
| `move_department(department, direction)` | POST | write | `up`/`down`; locks the rows (`FOR UPDATE`) and renumbers all to 1..n |
| `set_department_active(department, is_active)` | POST | write | Activates or deactivates |
| `delete_department(department)` | POST | delete | Turns Frappe's `LinkExistsError` into a clear message |

`helpdesk/tasky/api.py`: `create_project` and `update_project` take `department` (leaving it out
of an update keeps the project's department, an empty value clears it). `Project.validate`
refuses a newly picked inactive department on every save (helpdesk, Desk, REST or import); a
project keeps a department that was deactivated later. `get_projects` and
`get_project_detail` return `department`.

## Roles and task categories

Project member roles (`Project User.custom_role`): Project Manager, Functional Consultant,
Developer, DevOps Engineer, Support Engineer, **Digital Marketing Specialist**, **Social Media
Executive**, **Content Writer / Copywriter**, **Graphic Designer**, **Videographer cum
Editor**, **Motion Graphics Artist / Animator** and **Project Coordinator**.

Task categories (Task `custom_category`, HD Task Template Task `category`, and `CATEGORIES` in
`desk/src/pages/tasky/taskMeta.ts`): Functional, Development, DevOps, Support, **Digital
Marketing**, **Social Media**, **Content Writing**, **Graphic Design**, **Video**, **Motion
Graphics**, **Coordination**, Common (last).

`CATEGORY_TO_ROLE` in `helpdesk/tasky/api.py` decides who gets each task when a checklist is
generated from a template: members with the matching role take turns, and when nobody has that
role, every member takes turns.

| Category | Role |
| --- | --- |
| Digital Marketing | Digital Marketing Specialist |
| Social Media | Social Media Executive |
| Content Writing | Content Writer / Copywriter |
| Graphic Design | Graphic Designer |
| Video | Videographer cum Editor |
| Motion Graphics | Motion Graphics Artist / Animator |
| Coordination | Project Coordinator |

AI task estimates (`helpdesk/task_estimates.py`): when the AI isn't available and there are no
finished tasks of the same category yet, the new categories use `CATEGORY_TYPICAL_DAYS`
(Digital Marketing 2, Social Media 1, Content Writing 1, Graphic Design 1, Video 3, Motion
Graphics 3, Coordination 1 working days) before the per-project-type default. The AI prompt
also gives rough durations for designs and videos.

## Decisions

- **Project Coordinator has no manager powers.** Only members with the Project Manager
  project role manage a project (`helpdesk/tasky/permissions.py` `MANAGER_PROJECT_ROLE`, and
  `get_project_managers` in `helpdesk/work_reminders.py`, and the work-summary query). Giving
  coordinators those rights would change who can edit projects and approve tasks, so it is left
  for a separate decision.
- **Lead rotation stays among Developers** (`LEAD_ROTATION_ROLES` in `helpdesk/tasky/api.py`).
  Creative projects can still set a lead by hand.
- **Department is a custom field**, like the other fields helpdesk adds to its own Project,
  Project User and Task doctypes, so option and field changes reach existing sites on migrate.
- **Projects without a department** are listed last rather than hidden, so nothing goes missing
  before existing projects are assigned.

# Departments and creative roles

TBO is organised in eight departments: **ERP**, **Digital**, **Creative**, **GrowthX**,
**Internal / R&D**, **Web Development**, **Sales** and **CRM**. Every project can belong to one, and the Projects page groups projects by
department. Project members can also hold creative and digital roles, and template tasks in
the matching categories go to them.

## Where it is in the app

- **Settings → Departments** (System Managers and Agent Managers): the list in display order.
  Add a department, rename it (its projects move with it), set its heads, move it up or down,
  deactivate or activate it, or delete it. A department that projects still use can't be deleted; the
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

| Role | Never sees | Tickets |
| --- | --- | --- |
| **DM Employee** | the **ERP** department, and the support pages: Tickets, Customers, Contacts, Templates, Knowledge base, Support hours, Customer report | only tickets they raised |
| **ERP Employee** | the **Digital** department, the content calendar (even with a content role) and the work Calendar | works tickets like any agent, with the Tickets list ([Tickets list](#tickets-list)) |

The content calendar is opt-in for everyone else too: only the content team sees it, so a plain
agent with neither role (an ERP consultant, a developer) doesn't see it either; see
[content-calendar.md](content-calendar.md#who-sees-the-content-calendar).

Creative, GrowthX, Internal / R&D and projects with no department stay visible to both. System
Managers and Agent Managers see every department. **The Scoreboard is the one exception**: there
both teams see every department, so they can compete ([team-dashboard.md](team-dashboard.md#who-sees-what)).

- **What's hidden** (`hidden_departments()` in `helpdesk/tasky/permissions.py`, mapping
  `HIDDEN_DEPARTMENTS`): that department's projects and their tasks, in every list
  (`project_query`, `task_query`: Projects, My Work, Overview, Calendar, Desk) and when opened
  directly (`project_has_permission`, `task_has_permission`), and its chip in the department
  filters (`get_departments`).
- **No projects across the wall:** `Project.validate_department` refuses creating a project in,
  or moving one into, a department hidden from the person saving it ("You can't put a project in
  the ERP department."), so nobody files a project where they'd lose sight of it. System Managers
  and Agent Managers can file projects anywhere.
- **No assignments across the wall:** a ToDo `validate` hook (`check_assignment_department`)
  refuses giving a task in a hidden department to that person ("… can't be given tasks in the ERP
  department."), from any screen, the Desk or templates. It also refuses giving an ERP Employee a
  content post's task ("… can't be given content calendar tasks.",
  `check_can_take_content_task`, which hand-over checks before changing anything). An ERP
  Employee left on a content post's team gets no task from it (`HDContentPost.task_people`), so
  saving the post doesn't fail. This is needed because Frappe shares a
  task with its assignee, and a share would let them open it even though it's hidden from their
  lists.
- **Content calendar for ERP Employees** (`content_team.is_erp_only()`, unless they also edit
  content): they are never in the content team (`in_content_team()`), so the posts, Content,
  Performance and the content routes are hidden as for every non-member. On top of that, a
  content post's tasks (`Task.content_post` set) are left out of `task_query` and refused by
  `task_has_permission` even when assigned to them, whatever their project's department; one
  left on a post's team gets no task and no "your turn" notice from it
  (`HDContentPost.task_people`); and the sidebar hides the work Calendar, whose route
  (`WorkCalendar`) goes to Home (`ERP_EMPLOYEE_HIDDEN_ROUTES` in `pages/content/contentTeam.ts`,
  `authStore.isErpOnly`).
- **Support pages hidden from DM Employees** (`content_team.is_dm_employee()`, false for System
  Managers and Agent Managers; `authStore.isDmEmployee`): Support hours, Tickets, Customers,
  Contacts, Templates, Knowledge base and Customer report leave the sidebar, and their routes
  (`DM_EMPLOYEE_HIDDEN_ROUTES` in `pages/content/contentTeam.ts`, including single tickets,
  customers, contacts and articles) send them to Home; the command palette drops Knowledge Base.
  Tickets are also hidden on the server: `sees_no_tickets()` gives them the same ticket
  visibility as the Content Team (only tickets they raised themselves). Someone holding both
  walls counts as a DM Employee here.
- **ERP Employees work tickets** (owner, 2026-10-10: "Tickets must be visible for all ERP team
  members"): they keep Customers, Contacts, Templates and the Knowledge base like any agent,
  get the Tickets list ([below](#tickets-list)), and on the server see the tickets any agent
  would (`sees_no_tickets()` is false, so HD Ticket's `permission_query` and `has_permission`
  apply the usual team and assignment rules, never more). Support hours and the Customer
  report follow the usual rule too: Agent Managers and project managers only.
- **Inside a project they can see**, DM and ERP Employees, like every member who doesn't run
  it, see only their own tasks (assigned to them, given out by them or created by them); the
  Digital Marketing Head and DM Coordinators see every task of content calendar and Digital
  projects. The full matrix is in [workspace-pages.md](workspace-pages.md#who-sees-which-tasks).
- **Setting the walls: Settings → Agents.** Each agent row shows an "ERP team", "Digital
  team" or "Sales team" badge, and System Managers and Agent Managers set it from the agent's
  menu (Department wall: No wall, ERP team, Digital team, Sales team; the Sales team is the
  [Sales Employee wall](#sales-wall-sales-employee)). A "Content team" badge marks everyone who
  sees the content calendar (`get_content_team(users)`); the Digital team wall adds someone
  to it. Picking one gives the user that role and
  takes the others away; their other roles stay. API in `helpdesk/api/departments.py`:
  `get_department_walls(users)` and `set_department_wall(user, role)` (POST; `role` is
  `ERP Employee`, `DM Employee`, `Sales Employee` or empty; `WALL_ROLES`). Someone with more
  than one of those roles shows "More than one wall" until a choice is made.
- The walls go by department **name** ("ERP", "Digital"). Renaming either department in
  Settings → Departments turns its wall off until `HIDDEN_DEPARTMENTS` is updated. Projects with
  no department aren't walled, so set each project's department for the walls to apply.

## Sales wall: Sales Employee

The owner (2026-10-21): "Shahana is a salesperson. She wants to see the leads, proposals and
related things only. She doesn't want to see the tasks, the content calendar, things like
that." The **Sales Employee** role (created on install and migrate by
`content_team.ensure_role()`, home page `/helpdesk/leads`) makes an agent a salesperson in
the hub. `content_team.is_sales_employee(user)` is the one check; it is false for
Administrator, System Managers and Agent Managers, who are never walled. In the boot it is
`is_sales_employee` (`authStore.isSalesEmployee`).

Unlike the ERP and Digital walls it doesn't hide one department: it hides the hub's work
altogether, because a salesperson's work is leads, which live on the ERP site.

| Sees | Doesn't see, and can't open |
| --- | --- |
| **Leads**: the Overview, the list, the lead page, proposals and the documents chain up to the client documents | Home (it is their tasks and tickets, so `/helpdesk/home` opens Leads → Overview) |
| **Scoreboard** (the sales rows, [team-dashboard.md](team-dashboard.md#sales)) | Tickets and the support pages: Customers, Contacts, Templates, Knowledge base, Support hours, Customer report |
| **Notifications**, their own profile and preferences (the user menu), **Help & docs** | Projects, My Work, Board, Calendar, Timesheets, In progress, the work Overview, Team, Summaries, Performance, Stand-up |
| | The content calendar (Content, plans, the report) |

- **Sidebar and routes** (`SALES_EMPLOYEE_ROUTES` in `pages/content/contentTeam.ts`): an
  **allow list**, not a hide list like the other walls, so a page added later stays out of
  a salesperson's way until someone decides it is a sales page. `AppSidebar.vue` shows only
  those items, and the router (`desk/src/router/index.ts`) sends every other route to Leads
  (to the Scoreboard while Leads is switched off). The search card, the command palette
  (it finds tickets and articles), saved ticket views and the follow-up strip (it opens My
  Work) are left out for them.
- **Leads for every salesperson:** `can_use_leads` is true for a Sales Employee whatever the
  "Leads for" teams say, while Leads is on and they are an active agent
  ([leads.md](leads.md#who-sees-it)).
- **Documents chain:** a salesperson works the client documents; the **Project** and **UAT**
  steps show their status but don't open, and when the next step is the project's or the
  UAT's the header says "The project team takes it from here" instead of the button
  (`LeadDocuments.vue`). Creating the project is refused on the server anyway.
- **Server** (so nothing reaches them another way):
  - Projects and tasks: `project_query` and `task_query` return nothing (`1 = 0`), and
    `project_has_permission` and `task_has_permission` refuse every one, creating included,
    even on a project's team, with a task they created or one given to them before the wall.
    HD Pull Request follows the task. Timesheets: only their own (`timesheet_query`).
  - Tickets: `sees_no_tickets()` is true, so HD Ticket's `permission_query` and
    `has_permission` give them only tickets they raised themselves, as for DM Employees;
    `can_work_tickets` is false.
  - Content: they are never in the content team (`_in_content_team`, as for ERP Employees),
    so posts, campaigns and content tasks are refused; HD Content Campaign and HD Work
    Summary refuse them too, even for a customer whose project they are on.
  - `can_see_overview` (`helpdesk/api/work.py`) is false for them, which closes the Overview
    and Team APIs even to a salesperson who also holds Project Manager.
- **Left on a team, they hear nothing:** a content post gives them no task
  (`HDContentPost.task_people`), and `work_reminders.new_notification`, the one place every
  hub notice is made, skips a Sales Employee for the doctypes they can't open
  (`SALES_HIDDEN_DOCTYPES` in `content_team.py`: Project, Task, Timesheet, HD Ticket, HD
  Article, the content doctypes, HD Work Summary, HD Support Contract, project files and
  sign-offs, HD Standup). Scoreboard notices (HD Team Champion) still reach them.
- **No assignments:** the ToDo `validate` hook (`check_sales_assignment`, from
  `check_assignment_department`) refuses giving a Sales Employee a task ("Shahana Sales is on
  the Sales team and can't be given tasks.") or a ticket ("… can't be given tickets."), from
  any screen, the Desk or templates. Only a new or reopened assignment is refused, so work
  they held before the wall can still be closed. Assignment rules pass them over
  (`HelpdeskAssignmentRule.get_user`), and a customer's ticket owner or backup who is a Sales
  Employee counts as not working (`HDCustomer.ticket_owner_today`), so a new ticket never
  fails to save over them.
- **Stand-up:** not for them. It is filled from tasks, tickets and content posts, none of
  which they have, so they get no draft and no reminder (`standup.candidates`), and the page
  isn't in their sidebar.
- **Giving someone the role:** Settings → Agents → the agent's menu → Department wall →
  **Sales team: leads only, no tasks or tickets**. It replaces an ERP or Digital wall. The
  role can also be added on the user's Roles in the Desk.

## Tickets list

Separately from the walls, the Tickets list is for the people who work tickets:
`content_team.can_work_tickets()`, sent in the boot as `can_work_tickets`
(`authStore.canWorkTickets`). That is System Managers, Agent Managers and ERP Employees (unless
they also hold DM Employee, or only do content). Every other agent, a developer with no wall
for example, doesn't get it:

- the **Tickets** sidebar item is `ticketWorkersOnly` (`layoutSettings.ts`, filtered in
  `AppSidebar.vue`);
- the `TicketsAgent` (`/tickets`) and `TicketAgentNew` routes send everyone else to Home
  (`beforeEnter` in `desk/src/router/index.ts`);
- the command palette's **Tickets** entry is shown only to them (`CP.vue`). Typing `#<id>`
  still jumps to a ticket.

| Who | Tickets list and New ticket | Which tickets (server) |
| --- | --- | --- |
| Administrator | yes | all |
| System Manager, Agent Manager | yes | what their agent permissions allow |
| ERP Employee | yes | what any agent sees (teams, assignment) |
| Other agents (no wall) | no | what any agent sees; a ticket opens from a link |
| DM Employee, Sales Employee, Content Team | no | only tickets they raised |

The list gate only hides pages; which tickets someone sees is always HD Ticket's
`permission_query` and `has_permission`. Home and My Work list the tickets assigned to a person
through the same permissions, so they show up for the ERP team too.

## Data model

- **HD Department** (`helpdesk/helpdesk/doctype/hd_department`): `department_name` (Data,
  unique, also the record name via `field:department_name`, renamable), `sort_order` (Int, new
  departments go to the end), `is_active` (Check, default 1), `heads` (Table MultiSelect of
  users, reusing the child doctype **HD Content Alert Recipient**: one `user` link per row),
  `description`, `parent_department` (Link → HD Department, "Part Of": the main department
  whose group this one is in; empty for a main department). System Manager and Agent Manager
  have full access; Agent and Project Manager can read.
- **Project.custom_department**: Link → HD Department, defined in
  `helpdesk/setup/install.py` `get_custom_fields()` and applied on install and on every
  migrate. It is a standard filter.
- **Seeding**: `ensure_default_departments(names=DEFAULT_DEPARTMENTS)` (in `hd_department.py`)
  inserts any of the defaults that are missing and leaves existing, renamed or deactivated ones alone. It runs from
  `after_install` and from the patch `helpdesk.patches.v16_0_2.seed_departments` for existing
  sites. Patches run once, so a default deleted later stays deleted.

## API

`helpdesk/api/departments.py`:

| Method | HTTP | Permission | What it does |
| --- | --- | --- | --- |
| `get_departments(include_inactive=False)` | GET | read | Departments in order, each with `parent_department`, `project_count`, `heads` (`user`, `full_name`) and `head_roles` |
| `set_department_parent(department, parent=None)` | POST | write | Puts the department in `parent`'s group, or makes it a main department again (no `parent`); one level only |
| `add_department(department_name, description=None)` | POST | create | Adds one at the end |
| `rename_department(department, new_name)` | POST | write | `frappe.rename_doc`; projects follow |
| `move_department(department, direction)` | POST | write | `up`/`down`; locks the rows (`FOR UPDATE`) and renumbers all to 1..n |
| `set_department_active(department, is_active)` | POST | write | Activates or deactivates |
| `set_department_heads(department, heads)` | POST | write | Replaces the department's heads (a list of users, duplicates dropped; disabled or unknown accounts refused) |
| `delete_department(department)` | POST | delete | Refuses a main department with sub-departments; turns Frappe's `LinkExistsError` into a clear message |
| `get_department_walls(users)` | GET | System / Agent Manager | `{user: [wall roles]}` for Settings → Agents |
| `set_department_wall(user, role=None)` | POST | System / Agent Manager | Gives the agent DM Employee, ERP Employee or neither |
| `get_content_team(users)` | GET | System / Agent Manager | Which of `users` are in the content team, for the badge |

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

## Department groups

TBO has three main departments: **ERP** (with **GrowthX** and **Internal / R&D** under it),
**Digital** (with **Creative** and **Web Development**) and **Sales** (with **CRM**; the
owner, 2026-10-16). A department can be **part of** a main department
(`HD Department.parent_department`); a main department and its sub-departments form a
**group**, named after the main department.

- **Settings → Departments**: each row says "Part of ERP", "Main department of GrowthX,
  Internal / R&D" or "Main department". **Set group** (the network button) opens the row as a
  form: pick the main department, or "No group: a main department", then **Save group**. A
  main department that has sub-departments stays one (the form says so). System Managers
  and Agent Managers only.
- **One level** (`HDDepartment.validate_parent_department`): a department can't be part of
  itself or of a department that is itself part of another, and a main department with
  sub-departments can't join a group. A main department with sub-departments can't be
  deleted until they move out (or it can be deactivated).
- **Where groups count**: only the Scoreboard ([team-dashboard.md](team-dashboard.md)): the
  Departments view shows each group with its departments under it, the department filter
  takes a group, and every closed period stores a champion per group as well as per
  department. Projects keep exactly one department, and the Projects page, the Overview
  filter and every other list still go by department.
- **The walls are unchanged**: `HIDDEN_DEPARTMENTS` still names single departments (ERP,
  Digital), so putting Creative or Web Development in the Digital group doesn't hide them
  from ERP Employees, and GrowthX stays visible to DM Employees.
- **No department wall for Sales (decided 2026-10-19):** Sales and CRM projects are visible
  to everyone, like Creative and GrowthX. Leads themselves never live in the hub (they are
  read live from the ERP site, whose sales rules decide who sees which lead,
  [leads.md](leads.md)), so a department wall here would hide nothing; Sales projects and
  tasks, if any, are ordinary work. Salespeople themselves get the
  [Sales Employee wall](#sales-wall-sales-employee) (2026-10-21), which keeps them to the
  sales screens.
- **Setting the owner's groups**: `DEFAULT_GROUPS` in `hd_department.py`; `set_default_groups()`
  puts GrowthX and Internal / R&D under ERP, Creative and Web Development under Digital and
  CRM under Sales, only where a
  department has no group yet and both exist (a group someone set stays, and a renamed
  department is left alone). New sites get it on install (`ensure_default_departments`);
  existing sites from the patch `helpdesk.patches.v16_0_2.set_department_groups`, which runs
  once on deploy. Web Development, Sales and CRM came later: the patch
  `helpdesk.patches.v16_0_2.seed_sales_departments` adds only those three when missing
  (`ensure_default_departments(SALES_AND_WEB_DEPARTMENTS)`, so an older default someone
  deleted stays deleted) and then fills the groups the same careful way.
- **Where Sales counts**: salespeople's CRM activity is scored in **CRM**
  ([team-dashboard.md](team-dashboard.md#sales)); Sales' own projects, if any, count in Sales
  like any department.

## Department heads

Every department can have heads. `department_heads(department)` in
`helpdesk/tasky/permissions.py` is the one answer to "who heads department X": the enabled users
in the department's **Heads** setting plus the holders of a role mapped to it in
`DEPARTMENT_HEADS` (**Digital Marketing Head → Digital**, so the content calendar's approver
heads Digital without extra setup). For the whole team (no department) it returns the Agent
Managers. Heads are told when their department's Scoreboard champion is chosen, daily and for
every longer period ([team-dashboard.md](team-dashboard.md#champions-of-closed-periods)).
`departments_headed(user)` reads it the other way; heads get the TBO Smart app's management
insights for the departments they head (`manage_team`, read-only; see
[tbo-smart-api.md](tbo-smart-api.md#capabilities)).

- **Settings → Departments**: each row shows its heads ("Heads: Deepa Varma, everyone with
  Digital Marketing Head") or "No heads set". **Set heads** (the person-gear button) opens the
  row as a form: pick people, **Save heads** or Cancel (Esc). Only System Managers and Agent
  Managers (write permission on HD Department) can save; anyone else gets a permission error.
- Renaming a department keeps its heads.

## Decisions

- **A Project Coordinator runs the project's tasks, not the project.** Coordinators
  (`COORDINATOR_PROJECT_ROLE`, `can_coordinate_project` in `helpdesk/tasky/permissions.py`)
  see every task and create, assign, hand over, plan, hold, resume and review them; editing
  the project, its team, roles or lead, deleting, Sign-off, recurring schedules and invoicing
  stay with its managers. The full table is in
  [workspace-pages.md](workspace-pages.md#what-a-project-coordinator-may-do). They aren't
  project managers: they get no manager notices (`get_project_managers` in
  `helpdesk/work_reminders.py`) and don't generate customer summaries. The follow-up ladder
  does bring them in: from L2 an overdue task also goes to its coordinators and its
  department's heads, and a task waiting for review goes to them first
  ([follow-ups.md](follow-ups.md#the-ladder)).
- **Lead rotation stays among Developers** (`LEAD_ROTATION_ROLES` in `helpdesk/tasky/api.py`).
  This is deliberate, not a bug: the lead is the senior developer who answers for the build,
  and a coordinator already has the task powers a lead uses, so making one lead would add
  nothing. Creative projects can still set a lead by hand.
- **Department is a custom field**, like the other fields helpdesk adds to its own Project,
  Project User and Task doctypes, so option and field changes reach existing sites on migrate.
- **Projects without a department** are listed last rather than hidden, so nothing goes missing
  before existing projects are assigned.

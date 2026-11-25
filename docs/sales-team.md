# Sales team

**Status:** built 2026-11-25. This document is the living source of truth for the feature;
update it with every change.

A Sales Head sees the people on the sales team and manages them on **Sales team**
(Sales → Team, `/helpdesk/sales-team`): adds an agent to the team, changes which sales roles
they hold, or removes them from the team.

## Who

| Role | What they get |
| --- | --- |
| `Sales Head` (or System Manager) | The **Sales team** page and its actions. The same people as Assign sales targets (`can_assign_targets` in `helpdesk/sales_targets.py`), so the page reuses the boot flag `can_assign_sales_targets` and the sidebar's `salesHeadOnly`. |

## The team

Every enabled user holding one of the team roles (`TEAM_ROLES` in `helpdesk/sales_team.py`):

| Role | What it gives the person |
| --- | --- |
| `Sales User` | Leads and Today's calls; is given sales targets (docs/sales-targets.md). |
| `Presales Executive` | Is given sales targets; no Today's calls. |
| `Sales Employee` | The Sales department wall: the sales screens only, no tasks, projects or tickets (docs/departments.md). |

Administrator and Guest are never listed. Sales Heads and Sales Managers are not team members
unless they also hold a team role; a Sales Head can't give those manager roles here.

## Actions

All three go through one endpoint, `helpdesk.api.sales_team.set_member_roles(user, roles)`,
which gives the person exactly `roles` (a subset of the team roles):

- **Add to team**: picks one of the active agents not yet on the team (`candidates`) and at
  least one role.
- **Roles**: changes the team roles of someone on it; at least one stays.
- **Remove from team** (asks first): `roles = []`. Only the team roles are taken away. The
  account, the agent record and every other role stay, so they can be added back any time.
  Disabling an account stays with Settings → Agents (Deactivate agent).

## Rules (server side, `helpdesk/sales_team.py`)

- Only a Sales Head or System Manager may read the team or change it
  (`SalesTeamForbiddenError`, shown as "The sales team isn't open to you").
- Only the team roles can be given or taken; anything else is refused.
- Only an active agent with an enabled account can be added (or given roles).
- A Sales Head can't change the roles of an admin (System Manager, Agent Manager, Project
  Manager); a System Manager can.
- Giving `Sales Employee` takes away the ERP or Digital wall (`ERP Employee`,
  `DM Employee`), as Settings → Agents does: one department wall at a time.
- The User is saved with `ignore_permissions`, since a Sales Head has no write access on
  User; the role check above decides.

The roles are changed on the hub only. The CRM user sync (`helpdesk.integrations.crm.users`)
adds missing CRM users and roles but never takes a role away on the ERP site.

## Files

| File | What it holds |
| --- | --- |
| `helpdesk/sales_team.py` | `TEAM_ROLES`, the team, the candidates, and changing a person's roles. |
| `helpdesk/api/sales_team.py` | `get_team`, `set_member_roles`. |
| `helpdesk/tests/test_sales_team.py` | The rules above. |
| `desk/src/pages/sales-team/SalesTeam.vue` | The page: search, filter by role, Roles and Remove per person. |
| `desk/src/pages/sales-team/MemberRolesDialog.vue` | Add to team / change roles. |
| `desk/src/pages/sales-team/salesTeam.ts` | The types and each role's hint. |

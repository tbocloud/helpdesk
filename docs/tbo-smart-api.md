# TBO Smart app: hub API (v1)

The contract the TBO Smart mobile app (React Native, Expo) builds against on the **TBO Support
hub** (https://teams.teambackoffice.com). The ESS half (tboindia, `tbo_smart` app) is not part
of this repo and is not covered here.

- Code: `helpdesk/api/mobile.py` (every endpoint), `helpdesk/mobile_push.py` (push),
  `HD Mobile Device` (push tokens), HD Settings → **Mobile push** (switch).
- Tests: `helpdesk/tests/test_mobile_api.py`.
- Fixtures: `docs/tbo-smart-api/<endpoint>.json`, one real-shaped response per endpoint, for
  mocking.

`helpdesk.api.mobile` is a **thin façade**: each method calls the function the web pages use
(My Work, Home, tasky, the ticket controller, project files, follow-ups, the team views, the
Scoreboard) and only reshapes the answer. No rule lives here that the web decides elsewhere,
and every endpoint enforces the web's permissions.

## Basics

- **Base URL:** `https://teams.teambackoffice.com/api/method/helpdesk.api.mobile.<method>`.
- **Auth:** `Authorization: Bearer <access_token>` on every call (see Authentication).
  Don't send cookies (`credentials: "omit"`); see "CSRF" below.
- **Verbs:** reads are `GET` with query parameters; writes are `POST` with a JSON body
  (`Content-Type: application/json`). A write sent as GET is refused.
- **Who:** every method is for agents (active HD Agents, Agent Managers, admins). A customer
  account gets `PermissionError`. The user always comes from the token, never a parameter.
- **Envelope:** Frappe wraps the return value in `message`:

  ```json
  { "message": { "v": 1, "data": { … } } }
  ```

  Lists add paging: `{"v": 1, "data": [ … ], "next_cursor": 20, "has_more": true}`. Pass
  `cursor` (the last `next_cursor`) and `limit` (1–100, default 20) for the next page;
  `next_cursor` is `null` on the last page.
- **Versioning:** `v` is 1. Fields may be **added** in v1; nothing is renamed or removed. A
  breaking change ships as a new module (`helpdesk.api.mobile_v2`) with `v: 2`, and v1 keeps
  working until the app has moved.
- **Dates:** site time zone (Asia/Kolkata), `YYYY-MM-DD` or `YYYY-MM-DD HH:MM:SS[.ffffff]`.

### Errors

Frappe answers an error with an HTTP status and:

```json
{ "exc_type": "PermissionError", "_server_messages": "[\"{\\\"message\\\": \\\"…\\\"}\"]" }
```

(`docs/tbo-smart-api/error.json`). The app maps it to `{code, message}`: `code` from the status
(`401` expired/invalid token → refresh, `403` → `forbidden`, `404` → `not_found`, `417`/`400` →
`invalid` with the message shown to the user, `429` → `rate_limited`, `5xx` → `server`) and
`message` from the first `_server_messages` entry's `message`. The messages are written for
people and are safe to show as they are.

## Authentication: OAuth 2.0 Authorization Code + PKCE

Frappe's built-in OAuth provider. No API keys or passwords in the app.

### Owner setup on the hub (one time)

Create one **OAuth Client** on the hub (desk: `/app/oauth-client/new`; this is a Frappe
system record, so it is created in desk by a System Manager):

| Field | Value |
| --- | --- |
| App Name | `TBO Smart` |
| Skip Authorization | ✔ (staff app; no Allow/Deny screen) |
| Scopes | `all openid` (one per line or space separated, as the field takes it) |
| Redirect URIs | `tbosmart://oauth/callback` |
| Default Redirect URI | `tbosmart://oauth/callback` |
| Grant Type | `Authorization Code` |
| Response Type | `Code` |
| Allowed Roles | `Agent`, `Agent Manager` (only staff can sign in through it) |

Give the generated **Client ID** to the app developer. The **Client Secret is not used** by
the app (a phone can't keep a secret); PKCE protects the code instead. Optionally set
OAuth Provider Settings → Skip Authorization to `Auto`.

### PKCE on Frappe v15 (checked in frappe 15.121.1)

- **Supported.** `frappe.integrations.oauth2.authorize` accepts `code_challenge` and
  `code_challenge_method`; `frappe.oauth.OAuthWebRequestValidator.save_authorization_code`
  stores them on the OAuth Authorization Code, and `validate_code` checks the
  `code_verifier` at `get_token` (`S256`: base64url(sha256(verifier)) without padding, or
  `plain`). A code issued with a challenge is **deleted** if redeemed without a verifier.
- Send `code_challenge_method=S256` exactly (oauthlib only accepts `S256` and `plain`).
- **PKCE is optional on the server**, not enforced: a request without a challenge also gets a
  code. The app must always send it.
- **Public client works:** `get_token` loads the client by `client_id` and doesn't check a
  secret, so the token request needs only `client_id`, `code`, `redirect_uri` and
  `code_verifier`.
- The `id_token` (from the `openid` scope) is signed HS256 with the client secret, so the
  app can't verify it; read the profile from `openid_profile` (or `get_me`) instead.

### Flow

1. Make a `code_verifier` (43–128 chars) and `code_challenge = BASE64URL(SHA256(verifier))`.
2. Open in the system browser (`expo-auth-session` / `AuthSession`):
   `GET /api/method/frappe.integrations.oauth2.authorize?client_id=<id>&response_type=code&scope=all%20openid&redirect_uri=tbosmart%3A%2F%2Foauth%2Fcallback&state=<random>&code_challenge=<challenge>&code_challenge_method=S256`
   The hub shows its login page (password, or Microsoft login if set up), then redirects to
   `tbosmart://oauth/callback?code=…&state=…`. Check `state`.
3. Exchange the code (form-encoded POST):
   ```
   POST /api/method/frappe.integrations.oauth2.get_token
   grant_type=authorization_code&code=<code>&redirect_uri=tbosmart://oauth/callback&client_id=<id>&code_verifier=<verifier>
   ```
   → `{"access_token", "refresh_token", "expires_in": 3600, "token_type": "Bearer", "scope", "id_token"}`.
4. Call the API with `Authorization: Bearer <access_token>`.
5. **Refresh** before `expires_in` runs out, or on a 401:
   `grant_type=refresh_token&refresh_token=<refresh>&client_id=<id>` to the same `get_token`.
6. **Profile:** `GET /api/method/frappe.integrations.oauth2.openid_profile` (Bearer), or
   `helpdesk.api.mobile.get_me`.

### Sign-out and revoke

On sign-out the app, in this order:
1. `POST helpdesk.api.mobile.unregister_device` with the push token (needs the access token);
2. `POST /api/method/frappe.integrations.oauth2.revoke_token` with form body
   `token=<refresh_token>&token_type_hint=refresh_token`, then the same for the access token
   (`token_type_hint=access_token`). It always answers 200;
3. deletes both tokens from secure storage.

Revoked tokens fail at once (`OAuth Bearer Token.status = Revoked`). An admin can revoke a
lost phone's tokens in desk (OAuth Bearer Token list → filter by user → set Revoked), and
disabling the User stops all their tokens. The hub's endpoint guard (`helpdesk/auth.py`,
`block_endpoints`) lets `revoke_token` through, like `authorize` and `get_token`.

### CSRF

Frappe checks the CSRF token only for **cookie sessions** (`HTTPRequest.validate_csrf_token`
returns early when the session has no `csrf_token`). A Bearer request sets the user through
`frappe.auth.validate_oauth` with no session data, so POSTs need no CSRF header. If the
app's HTTP client also sent the browser's `sid` cookie, Frappe would resume that cookie
session and ask for CSRF: keep cookies out of API calls.

### Files

Private files (`/private/files/…`, project files, ticket attachments) download with the same
`Authorization: Bearer` header; Frappe checks the user's permission on the file. Uploads go
to `POST /api/method/upload_file` (multipart, `is_private=1`, `doctype=HD Ticket`,
`docname=<ticket>`), and the returned File `name` goes into `reply_ticket.attachments`.

## Endpoints

`GET` unless marked POST. "Fixture" is the file under `docs/tbo-smart-api/`.

### Me and home

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_me` | – | `Me`: user, full_name, image, roles, is_agent, is_manager, `can` {team, projects_health, sla_summary, escalations, approvals}, departments, teams | Any agent. `is_manager` = sees the overview (Project Manager role, admins, project leads). Fixture `get_me.json` |
| `get_home` | – | `HomeCounts` | Any agent; counts from My Work and Home's day. Fixture `get_home.json` |
| `get_home_bundle` | – | `{me, counts, tasks}` (tasks = first page of `get_tasks`) | **Call this at launch**: one round trip. Fixture `get_home_bundle.json` |
| `get_action_plan` POST | `refresh` (bool) | `{steps: [{id, text, detail, route}], generated_at, source: "ai"\|"rules", stale, reason}` | Call right after `get_home_bundle` (it reuses the day that call built). The AI may take seconds; `refresh` is rate limited by the hub. Fixture `get_action_plan.json` |

`HomeCounts`: `open_tickets`, `awaiting_reply`, `tasks_open`, `tasks_due_today`,
`tasks_overdue`, `tasks_on_hold`, `tasks_in_review`, `escalated_to_head` (own tasks at L2+),
`approvals` (tasks waiting for my review), `unread_notifications`.

### Tasks

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_tasks` | `group?` (overdue, today, upcoming, on_hold, in_review), `cursor`, `limit` | page of `Task` (no description/activity) | My own open tasks only (My Work), overdue first. Fixture `get_tasks.json` |
| `get_task` | `task` | `Task` + `description` (HTML), `activity`, `pull_requests` | Anyone who may read the task (#94 visibility: members only their own, leads/coordinators/managers the project's). Fixture `get_task.json` |
| `start_task` POST | `task` | `Task` detail | Starts an Open task (status Working, timer running) or resumes a paused timer. Write permission. Fixture `task_action.json` |
| `pause_task` POST | `task` | `Task` detail | Banks the time; stays Working |
| `complete_task` POST | `task`, `hours_worked` (>0, ≤24), `notes` (required) | `Task` detail | Logs a timesheet; a review project moves it to Pending Review |
| `hold_task` POST | `task`, `reason`, `note?` | `Task` detail | `reason` is one of the hub's: `Laptop / system issue`, `Leave`, `Waiting on customer`, `Waiting on another task`, `Other` |
| `resume_task` POST | `task`, `extend_due_date` (default true) | `Task` detail | The days on hold are added to the due date |
| `hand_over_task` POST | `task`, `teammate`, `reason` (required) | `{task, handed_to}` | The assignee (or the project's lead/coordinator). The task may leave the user's view, so no detail comes back. Fixture `hand_over_task.json` |
| `request_help` POST | `task`, `teammate`, `task_name` (required), `description?`, `due_date?` | `{task, help_task}` | The teammate gets a new task; this one waits on it. Fixture `request_help.json` |
| `review_task` POST | `task`, `approve` (bool), `note` (required when sending back) | `Task` detail | The project's manager, lead or coordinator only |
| `add_task_comment` POST | `task`, `content` | one activity item | Anyone who can read the task. Fixture `add_task_comment.json` |
| `get_teammates` | `task?` | `[{user, full_name, image, on_leave}]` | Active agents; for a task, its project team unless the user manages the project. Fixture `get_teammates.json` |

`Task`: `name`, `subject`, `project`, `project_name`, `customer`, `status` (Open, Working,
Pending Review, On Hold, Completed, Cancelled), `group`, `exp_end_date`, `is_overdue` (the
hub's rule: past due, or due today and past its estimate; a held task is never overdue),
`is_key`, `is_milestone`, `priority`, `assignees`, `assigned_by` {user, full_name},
`hold_reason`, `hold_note`, `hold_days`, `escalation` {level, label} or null, `timer`
{state: running|paused|idle, started_at, logged_hours}, `expected_hours`, `waiting_on`,
`risks` (sentences), `can_approve`.

Activity item: `{id, at, who, kind, type, text, data}`. `kind` is the app's group (status,
time, comment, assign); `type` is the hub's own kind (created, assigned, unassigned, status,
due, estimate, note, comment, time) and `data` its values (`from`/`to`, `hours`, `to_name`, …).
The app words each type the way the web's activity list does.

### Tickets

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_tickets` | `view` (mine, unassigned, team, all-open), `search?` (ticket number or subject words), `cursor`, `limit` | page of `Ticket` (no conversation), soonest SLA first | Open and paused tickets the user can see (`frappe.get_list`). `team` = the user's HD Teams. Fixture `get_tickets.json` |
| `get_ticket` | `ticket` | `Ticket` + `conversation` + `statuses` | Read permission on the ticket. Fixture `get_ticket.json` |
| `reply_ticket` POST | `ticket`, `message` (plain text), `attachments?` (File names) | `Ticket` detail | Write permission; same path and side effects as the agent page (`HD Ticket.reply_via_agent`: email to the customer, status update, SLA). Only files the user uploaded may be attached. 60/min per IP |
| `comment_ticket` POST | `ticket`, `message` | `Ticket` detail | Write permission. Internal note (`HD Ticket.new_comment`); @mentions notify as on the web. No attachments in v1 (`new_comment` types them as strings but reads them as objects). 60/min per IP |
| `set_ticket_status` POST | `ticket`, `status` | `Ticket` detail | Write permission; `status` must be one of the enabled HD Ticket Statuses (`statuses` in `get_ticket`) |
| `assign_ticket` POST | `ticket`, `agent` | `Ticket` detail | Write permission; `agent` must be an HD Agent. Replaces the current assignees |

`Ticket`: `name` (string), `subject`, `customer`, `contact`, `raised_by`, `priority`, `status`,
`status_category` (Open = waiting on us, Paused = waiting on the customer or a task),
`sla_due`, `sla_kind` (first_response until the first reply, then resolution), `sla_breached`,
`sla_due_soon` (within 4 hours), `assigned_to` (user id), `assignees` [{user, full_name}],
`team`, `opened_at`, `awaiting_reply`, `escalation_level`.

Conversation message: `{id, kind: customer|agent|note, author, author_email, at, body (plain
text), body_html, attachments: [{name, file_name, file_url}]}`, oldest first.

### Projects and files

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_projects` | `status` (default Open; empty for all), `cursor`, `limit` | page of `Project` | Projects the user can see (tasky.get_projects). Fixture `get_projects.json` |
| `get_project_files` | `project`, `folder?`, `for_me?` | `{project, folder, folders, files, superseded_hidden, can_upload}` | Read permission on the project. One folder at a time (top level by default) with its subfolders; `for_me` lists the files for the user from every folder. Superseded files are hidden and counted. Fixture `get_project_files.json` |
| `get_file` | `project`, `file` | `{name, file_name, file_url, size, kind, text}` | Read permission on the project, and the file must be attached to it. `text` only for .md/.markdown/.txt up to 2 MB; download anything else from `file_url` with the Bearer header. Fixture `get_file.json` |

`Project`: `name`, `project_name`, `customer`, `department`, `status`, `my_role` (project
role, or Project Lead), `lead`, `open_tasks` (mine), `files`, `for_you` (current files marked
for me), `expected_end_date`.

`ProjectFile`: `name`, `file_name`, `file_url`, `folder` (path like `Prompts/Phase 1`, "" at
the top), `folder_id`, `kind` (extension), `size` (bytes), `modified`, `uploaded_by`, `for_you`,
`status` (Active or Superseded), `status_note`, `can_preview`.

### Notifications

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_notifications` | `cursor`, `limit`, `unread_only?` | page of `AppNotification` + `unread` | Only the user's own (HD Notification, the web's bell), newest first. Fixture `get_notifications.json` |
| `mark_notifications_read` POST | `names` (list) or `"all"` | `{unread}` | Only the user's own notifications change |

`AppNotification`: `name`, `site: "hub"`, `type` (Assignment, Mention, Reminder, Reaction,
Task Completed), `title`, `body`, `at`, `read`, `doctype`, `reference`, `route` (the web
path), `app_route` (`/task/…`, `/ticket/…`, `/project/…`, or null), `from`.

### Devices and push

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `register_device` POST | `token`, `platform` (ios, android), `app_version?` | `{name, platform, token_type, app_version, last_seen}` | Call at every launch after sign-in. Upserts by token; a token last registered by someone else moves to this user (the phone changed hands). 30/min per IP. Fixture `register_device.json` |
| `unregister_device` POST | `token` | `{removed}` | Only the user's own token is removed. Fixture `unregister_device.json` |

**HD Mobile Device**: user, platform, token (unique), token_type (Expo for
`ExponentPushToken[…]`/`ExpoPushToken[…]`, else FCM), app_version, last_seen. Permissions:
System Manager; agents read and delete their own (`if_owner`). Rows are written only
through the two endpoints.

**Push** (`helpdesk/mobile_push.py`), when HD Settings → **Mobile push** is on (default
off):
- Every new HD Notification of type Assignment, Mention, Reminder or Task Completed is
  queued (after commit) to the recipient's Expo tokens. Notices kept for the follow-up
  digest (`skip_delivery`) aren't pushed, like chat and email. Reactions aren't pushed.
- Sent to `https://exp.host/--/api/v2/push/send` in batches of 100. A
  `DeviceNotRegistered` answer deletes that token.
- Payload (`push_payload.json`): `title`/`body` as in the notification list, `sound`,
  and `data` = `{site: "hub", doctype, name, route, app_route, notification}`. The app
  deep-links to `app_route`, else falls back to the list.
- Failure-safe: any error is logged to the Error Log ("Mobile push not queued" / "Mobile
  push failed") and never stops the notification.
- FCM tokens are stored but not sent to yet; the app should register its **Expo** push token
  (`getExpoPushTokenAsync`). No Expo access token is needed while "Enhanced push security" is
  off in the Expo project.

### Manager views

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_team` | – | `{people: [TeamMember], totals}` | Project managers, leads and admins (`get_team_workload`); others get 403. Fixture `get_team.json` |
| `get_team_member` | `user`, `cursor`, `limit` | page of `Task` | The same people, for someone on their projects (`get_my_work(user)`). Fixture `get_team_member.json` |
| `get_escalations` | `cursor`, `limit` | page of `Escalation` (L2+, highest level and longest wait first) | System and Agent Managers, like Overview → Follow-ups. Fixture `get_escalations.json` |
| `nudge` POST | `doctype` (Task, HD Ticket), `name`, `message` (≤500) | `{notified}` | Admins for anything; a project's manager, lead or coordinator for its tasks. The owners get a Reminder (bell, chat or email, push) and the item gets a note. Fixture `nudge.json` |
| `reassign` POST | `doctype`, `name`, `to`, `reason` (required for tasks) | as `hand_over_task` / `assign_ticket` | Tasks go through `hand_over_task` (the lead or coordinator hands over the whole task); tickets through `assign_ticket` |
| `get_approvals` | – | `[Approval]` (kind review) | Managers, leads and coordinators of projects; others get 403. Decide with `review_task`. Fixture `get_approvals.json` |
| `get_projects_health` | – | `[ProjectHealth]` | Same as `get_team` (the portfolio). Fixture `get_projects_health.json` |
| `get_sla_summary` | – | `{open, new_today, breached, first_reply_overdue, breaching_soon, unassigned, waiting_on_customer, oldest_unassigned}` | Same as `get_team`. Fixture `get_sla_summary.json` |
| `get_scoreboard` | `period` (today, week, month, quarter, half, year), `department?` | `{period, period_label, range, champion, me, leaders (top 10), departments}` | Every agent (the Scoreboard is open to all). Fixture `get_scoreboard.json` |

`TeamMember`: `user`, `full_name`, `image`, `on_leave`, `leave` {to_date, half_day},
`open_tasks`, `working`, `in_review`, `on_hold`, `overdue`, `due_this_week`, `done_this_week`,
`tickets`, `sla_breached`, `working_on`, `next_due`.

`Escalation`: `id` (`Task:TASK-…`), `kind` (task, ticket), `doctype`, `ref`, `title`, `owners`,
`level`, `level_label`, `days`, `severity`, `reason`, `route`, `app_route`.

## Where the app's types differ (src/api/types.ts)

Decided per field; "app" means change `types.ts`, "hub" means a later hub change.

| App type | Difference | Change |
| --- | --- | --- |
| all | Responses come wrapped: `message.v`, `message.data`; lists add `next_cursor`/`has_more` | app: unwrap in `client.ts` |
| `Me` | `department` (one) → `departments` (list); adds `is_agent`, `can` | app |
| `HomeCounts` | adds `tasks_in_review`, `approvals` | app (additive) |
| `ActionPlan` | steps have no `detail` on the hub (always ""); adds `source`, `stale`, `reason`; `route` only for task steps | app: hide empty detail |
| `Task` | `assigned_to` → `assignees` (list); `assigned_by` is `{user, full_name}` not `Person.role`; adds `group`, `is_overdue`, `customer`, `priority`, `risks`, `can_approve`; `description`/`activity` only in `get_task` | app: use `group`/`is_overdue` from the server instead of `taskGroup()` |
| `TaskStatus` | the hub also has `Cancelled` | app |
| `HoldReason` | the hub's list is `Laptop / system issue`, `Leave`, `Waiting on customer`, `Waiting on another task`, `Other` | app: use the hub's options (they drive reports) |
| `TaskActivity` | `{id, at, who, kind, type, text, data}`; `text` only on comments and notes; kind `hold`/`escalation` don't exist (holds are status changes) | app: word items from `type` + `data` |
| `askForHelp(name, to, note)` | `request_help` needs `task_name` (the helper task's title) | app: add a title field |
| `Ticket` | `assigned_to` is a user id, not a full name (the mocks compare with `full_name`); adds `assignees`, `status_category`, `sla_kind`, `sla_breached`, `sla_due_soon`; `conversation` only in `get_ticket` | app |
| `TicketStatus` | statuses come from the hub (`statuses` in `get_ticket`), not a fixed union | app |
| `TicketMessage` | adds `author_email`, `body_html`; attachments are `{name, file_name, file_url}`, no `size` | app |
| `TicketView` | the hub adds `all-open` | app (additive) |
| `Project` | adds `status`, `lead`, `expected_end_date` | app (additive) |
| `ProjectFile` | `kind` is any extension (not only md/pdf); `size` in bytes; `status` is Active/Superseded (no Final/Draft/Needs review on the hub); adds `file_url`, `folder_id`, `can_preview`; files are listed one folder at a time | app |
| `AppNotification` | `audience` is a prototype field (drop); adds `type`, `doctype`, `reference`, `app_route`, `from`; `route` is the web path, open `app_route` | app |
| `TeamMember` | `attendance`/`checked_in_at`/`leave_balance` are ESS data, not on the hub; `score`/`on_time_pct` come from `get_scoreboard`; `escalated` isn't counted per person (use `get_escalations`); tasks load per person with `get_team_member` | app: merge ESS and Scoreboard data by email |
| `Escalation` | `owner` (one name) → `owners` (list); `since` → `days`; adds `level_label`, `severity`, `route`, `app_route` | app |
| `Approval` | `submitted` → `due`; only `review` comes from the hub (leave and expense are ESS) | app |
| `ProjectHealth` | no `rag` and no hours: the hub has no project health rule or project hours yet. Show `overdue` and `next_milestone.is_overdue` | hub, if the owner wants a RAG rule (then it's added to the portfolio for the web too) |
| `SlaSummary` | adds `new_today`, `first_reply_overdue`, `waiting_on_customer` | app (additive) |
| `Scoreboard` | `range` is `{start, end}`; `champion` is the dashboard's card (`name`, `score`, `reasons`, `breakdown`); `me.delta_rank` isn't tracked; breakdown items are `{key, points, detail}` | app |

## Owner setup checklist

1. Create the **OAuth Client** above and send its Client ID to the app developer.
2. Turn on **Settings → General → Mobile app → Mobile push** once the app ships with push.
3. Nothing else: the doctype and the setting arrive with `bench migrate`.

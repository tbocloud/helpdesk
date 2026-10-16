# TBO Smart app: hub API (v1)

The contract the TBO Smart mobile app (React Native, Expo) builds against on the **TBO Support
hub** (https://teams.teambackoffice.com). The ESS half (tboindia, `tbo_smart` app) is not part
of this repo and is not covered here.

- Code: `helpdesk/api/mobile.py` (every endpoint), `helpdesk/api/mobile_auth.py` (single
  sign-in with Microsoft), `helpdesk/offboarding.py` and `helpdesk/api/offboarding.py`
  (offboarding), `helpdesk/mobile_push.py` (push),
  `HD Mobile Device` (push tokens), HD Settings → **Mobile push** (switch),
  `helpdesk/competition.py` (Compete: ranks, streaks, bests, badges, the weekly challenge;
  `HD Badge Award`), `helpdesk/team_insights.py` (management insights), the snooze in
  `helpdesk/follow_ups.py` (`HD Follow Up Snooze`), `helpdesk/repeat_issues.py` (repeat
  issues).
- Tests: `helpdesk/tests/test_mobile_api.py`, `helpdesk/tests/test_mobile_competition.py`,
  `helpdesk/tests/test_mobile_auth.py`, `helpdesk/tests/test_offboarding.py`,
  `helpdesk/tests/test_repeat_issues.py`.
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
disabling the User revokes all their tokens (see [Offboarding](#offboarding)). The hub's endpoint guard (`helpdesk/auth.py`,
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

## Single sign-in with Microsoft

The app asks for **one** login: Microsoft (Entra ID). Each site then decides access from its
own users and roles. Both TBO sites already offer "Login with Office 365", so every staff
member has an account in TBO's tenant. The per-site Frappe OAuth above stays as it is (the
app's fallback, and what single sign-in hands over to): the tokens issued here are ordinary
OAuth Bearer Tokens, so revoke and every endpoint work unchanged. They come **without a
refresh token**, so access never outlives the Microsoft account (see [Offboarding](#offboarding)).

Only the hub's side is in this repo. tboindia needs the same endpoint in its own app.

### Flow

1. The app signs in with Microsoft: Authorization Code + PKCE as a public client
   (`expo-auth-session`), authority `https://login.microsoftonline.com/<tenant id>/v2.0`,
   scopes `openid profile email offline_access`, a random `nonce`. Microsoft returns an
   **ID token** (and its own refresh token, which stays on the phone for a silent re-login).
2. The app sends the ID token to each site:
   ```
   POST /api/method/helpdesk.api.mobile_auth.exchange_microsoft_token
   {"id_token": "<Microsoft ID token>", "nonce": "<the nonce from step 1>"}
   ```
   No Authorization header and no cookies.
3. The answer:
   ```json
   { "message": { "v": 1, "data": {
       "access_token": "…", "expires_in": 3600,
       "token_type": "Bearer", "scope": "all openid",
       "user": "anjali@teambackoffice.com", "full_name": "Anjali Pillai" } } }
   ```
4. From here it is the normal flow: `Authorization: Bearer`, and revoke the access token on
   sign-out. There is **no refresh token**: before `expires_in` runs out (or on a 401), the
   app gets a fresh ID token from Microsoft (silently, with Microsoft's own refresh token)
   and exchanges it again. Microsoft refuses that for an account TBO has disabled, so the
   app's access ends within the hour. `get_token` with `grant_type=refresh_token` has
   nothing to refresh: these tokens are stored with no refresh token.

Errors (the message is safe to show):

| Status | When | App |
| --- | --- | --- |
| `401` `AuthenticationError` | the ID token failed a check below | sign in with Microsoft again (not a refresh) |
| `403` `PermissionError` | single sign-in is off on this site, or "Your TBO account isn't set up for TBO Support." | show the message; offer the per-site sign-in |
| `429` | more than 30 exchanges a minute from one IP address | retry later |

### What the hub checks

`helpdesk.api.mobile_auth.exchange_microsoft_token(id_token, nonce=None)`: guest, POST only,
rate-limited per IP address (30 a minute: an office shares one address).

1. Single sign-in is on and the tenant ID, app client ID and OAuth client are set, and the
   OAuth Client still allows `all openid` (checked on every exchange, because issuing a token
   directly skips the scope check Frappe's grant flows make; also checked when the switch is
   saved).
2. **Signature:** RS256 only, with the key Entra names in the token's `kid`, from the
   tenant's JWKS (`https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys`). PyJWT's
   `PyJWKClient` caches the keys for an hour per worker and refetches when Microsoft rotates
   to a key it hasn't seen. `none` and HS256 tokens are refused.
3. **Claims:** `exp`, `nbf`, `iat`, `iss`, `aud`, `tid` and `sub` must be present;
   `iss` = `https://login.microsoftonline.com/<tenant>/v2.0`; `tid` = the tenant;
   `aud` = the mobile app's client ID; `exp`/`nbf` with 60 s leeway.
4. **Fresh:** issued (`iat`) at most 10 minutes ago. The app exchanges the token right after
   signing in; this also bounds replay.
5. **Nonce:** when the app sends `nonce`, the token's `nonce` must equal it (constant-time
   compare).
6. **Once:** the token's `uti` (Entra's token id; `jti` if present instead) is stored in Redis
   with `SET NX` until the token expires (plus leeway). A second exchange of the same token on
   the same site is refused. A token without either is refused.
7. **User:** the first of `email`, `preferred_username`, `upn` is matched to a User's email
   (case-insensitively, by the database collation). The User must exist and be enabled, be
   an active HD Agent (or, without an agent record, have Agent or Agent Manager), and have one
   of the OAuth Client's Allowed Roles (the same rule Frappe's own sign-in applies). Users are
   never created. Every one of these refusals gives the same 403 message, so the endpoint
   doesn't reveal which accounts exist.
8. **Token:** issued by Frappe's own OAuth server (`get_oauth_server().bearer.create_token`
   and the validator's `save_bearer_token`): the same generator, `expires_in` 3600 and
   storage as `get_token`, linked to the configured OAuth Client with scopes `all openid`.
   No refresh token (`create_token(refresh_token=False)`): a refresh at `get_token` would
   never ask Microsoft, so it would keep a removed employee in for as long as they kept
   refreshing.

A refusal writes an Error Log titled "TBO Smart Microsoft sign-in refused" whose message is
the reason class only (`InvalidAudienceError`, `wrong_tenant`, `stale_token`, `replayed`,
`unknown_user`, `not_agent`, …); never the token or the email. It is inserted deferred,
because the refused request rolls back.

The endpoint guard (`helpdesk/auth.py`, `block_endpoints`) already lets every
`/api/method/helpdesk.*` path through, so it needs no allow-list entry.

### Security notes

- **Why an ID token, not an access token.** An ID token is issued *to our app*: its `aud` is
  the mobile app's client ID, it is signed by Entra with keys published for the tenant, and
  it names the person. A Microsoft Graph access token is meant for Graph only (its `aud` is
  Graph, and Microsoft says its format can change and isn't for third parties to validate),
  so accepting one would let any app that got a Graph token for the user sign in here.
- **Audience-bound, tenant-pinned, signature-verified.** A token issued to another app, or by
  another tenant (including personal accounts and `common`), fails `aud`, `iss` or `tid`; a
  forged or altered one fails the signature. The tenant and client IDs must be GUIDs, so the
  site can't be pointed at `common`.
- **Replay.** ID tokens live about an hour. The hub accepts one only within 10 minutes of
  issue, only once per site (`uti` in Redis), and, with the nonce, only for the sign-in the
  app started. A token leaked from a phone or a log is still only good for 10 minutes and
  one exchange. The app should always send the nonce.
- **Identity mapping.** `email`/`preferred_username`/`upn` are set by TBO's tenant admins
  (tenant-pinned), the same values "Login with Office 365" on the web already trusts.
- **Turning someone off.** Disabling the User in Frappe blocks the exchange at once and
  revokes their existing tokens; deactivating their HD Agent blocks the exchange too.
  Disabling or deleting them in Entra stops new Microsoft sign-ins, so their last site token
  dies within the hour, and the hourly [offboarding](#offboarding) job disables the User.
- **No secrets.** The Entra app is a public client with no secret; the hub only needs the
  tenant's public keys.

### Owner setup (one time)

1. **Entra app registration** (Microsoft Entra admin center → App registrations → New):
   name `TBO Smart`, single tenant ("Accounts in this organizational directory only").
   - Authentication → Add a platform → **Mobile and desktop applications**, redirect URI
     `tbosmart://oauth/callback` (add the `msauth.<bundle id>://auth` URI too if the app
     uses MSAL).
   - Advanced settings → **Allow public client flows: Yes**. No client secret.
   - API permissions: Microsoft Graph delegated `openid`, `profile`, `email`,
     `offline_access` (`User.Read` optional). Grant admin consent so staff don't see a
     consent screen.
   - Optional: Token configuration → add the optional claim `email` to the ID token (the hub
     falls back to `preferred_username`, which is the sign-in address, when it's missing).
2. Note the **Directory (tenant) ID** and the **Application (client) ID** (Overview) and give
   the client ID to the app developer.
3. On the hub, in **Settings → General → Mobile app** (System Managers): fill in
   **Microsoft tenant ID**, **Mobile app client ID** and **OAuth client for TBO Smart** (the
   OAuth Client from "Owner setup on the hub" above; its scopes must include `all openid`),
   then switch on **Single sign-in with Microsoft**. The switch stays off by default and only
   System Managers can see or change these settings.
4. Do the same on tboindia once its endpoint exists.

## Offboarding

The owner's rule: Microsoft is the only sign-in for TBO staff. When someone leaves, TBO
disables their Microsoft account, and that must end their access to the hub too.

### What the hub does

1. **Single sign-in issues no refresh token** (above). An hour after the last exchange the
   app needs a new Microsoft ID token, which Microsoft won't issue to a disabled account.
2. **A disabled user has no access.** Frappe already refuses them everywhere: a Bearer token
   (`OAuthWebRequestValidator.validate_bearer_token` checks the User is enabled), a cookie
   session (`Session.resume`) and API keys. On top of that, disabling a User revokes all
   their OAuth Bearer Tokens (`helpdesk.offboarding.revoke_tokens_of_disabled_user`, a User
   `on_update` doc event), so enabling the User again doesn't bring old phones back. This
   includes tokens from the per-site OAuth sign-in above, which still carry refresh tokens.
3. **Automatic offboarding from Entra** (`helpdesk.offboarding.run`, hourly at :40, **off by
   default**). It reads the tenant through Microsoft Graph with app-only auth, reusing the
   Entra app (Connected App) chosen in HD Meeting Settings: `GET /users?$select=id,
   accountEnabled,mail,userPrincipalName,otherMails,proxyAddresses`, following every
   `@odata.nextLink`. For each **enabled** hub User whose email is at one of the company
   domains:
   - an address (mail, UPN, other mails or an SMTP alias) on an enabled account: kept;
   - on accounts that are all disabled: disabled, reason **Disabled in Microsoft**;
   - on no account: disabled, reason **Not in Microsoft**. Deleted users drop out of
     `/users` at once (they sit in Entra's recycle bin for 30 days), so this covers
     deletion without reading `deletedItems`.

   Disabling saves the User (which revokes their tokens), writes an **HD Offboarding Log**
   (user, reason, when) and, once per run, tells the Agent Managers in one notification
   (helpdesk panel plus email or chat). Nothing is unassigned, so tickets and tasks keep
   their history.
4. **TBO Chat follows.** A User who is disabled (by this job or by hand) or an HD Agent who
   is deactivated is removed from the Chatwoot account, and an HD Offboarding Log row with
   action **Removed from TBO Chat** records it. See [chatwoot-sso.md](chatwoot-sso.md).

### Safety rules

- Administrator, Guest, every **System Manager** and the automation user (HDS Hub Settings)
  are never touched, so a break-glass admin can't be locked out by the job.
- Only users at the configured **company email domains** are checked; customers and
  partners at other domains never are.
- Nobody is changed when Graph fails on any page (an error, throttling, a network failure),
  when it returns nobody, or when it returns nobody at the company domains (a wrong tenant
  or domain list). The run stops with an Error Log titled "Offboarding from Microsoft
  stopped".
- **Dry run** (on by default once switched on) finds who would go and changes nothing.
- **Limit** (default 5): when more people would be disabled in one run, nobody is, and
  System Managers get one alert listing them (repeated only when the list changes). Raise
  the limit for a planned mass exit, or disable those people by hand.
- Shared mailboxes are disabled accounts in Entra: a hub User for one (at a company domain,
  without System Manager) would be offboarded. Run **Preview** before turning dry run off.

### Settings (Settings → General → Offboarding, System Managers only)

| Setting | Field | Default |
| --- | --- | --- |
| Disable people removed from Microsoft | `offboard_removed_microsoft_users` | off |
| Company email domains (one per line, stored lowercase) | `offboarding_domains` | – |
| Dry run | `offboarding_dry_run` | on |
| Most people disabled per run | `offboarding_max_disables` | 5 |

Switching it on needs the domains, a limit of at least 1 and a Microsoft app in HD Meeting
Settings. The fields are permlevel 1 (System Managers). The page also has:

- **Preview** (`helpdesk.api.offboarding.preview_offboarding`, POST, System Managers): who a
  run would disable now and why, changing nothing; works with the switch off.
- **Run now** (`helpdesk.api.offboarding.run_offboarding`, POST, System Managers): the hourly
  job at once, with the saved dry run and limit.
- **Recently disabled**: the last ten HD Offboarding Log entries.

Both buttons sign in to Graph afresh, so a permission granted a minute ago is used. A Graph
refusal shows Microsoft's message; a 403 without User.Read.All in the token says to grant it.

### Owner steps (the code can't do these)

1. **Grant the Graph application permission User.Read.All** to the Entra app chosen in HD
   Meeting Settings (Entra → App registrations → the app → API permissions → Microsoft Graph
   → Application permissions → User.Read.All), then **Grant admin consent**.
2. **Make Office 365 the only way in, on the web too.** In **System Settings** on both sites
   (the hub and tboindia): turn on **Disable Username/Password Login**, and turn off **Login
   with email link**. Check "Login with Office 365" works for you first.
3. **Keep at least one break-glass Administrator.** With username/password login disabled,
   Frappe refuses password login for everyone, Administrator included, so keep a System
   Manager whose Microsoft account isn't tied to one person, and keep server access for the
   last resort: `bench --site <site> browse --user Administrator` opens a session without a
   password, and `bench --site <site> console` can turn password login back on
   (`frappe.db.set_single_value("System Settings", "disable_user_pass_login", 0)`). The
   offboarding job never disables Administrator or a System Manager.
4. In **Settings → General → Offboarding**: add the domains (e.g. `teambackoffice.com`),
   switch it on, save, press **Preview** and check the list. When it is right, turn **Dry
   run** off and save.
5. On tboindia, the same rules need its own code (not in this repo).

## Endpoints

`GET` unless marked POST. "Fixture" is the file under `docs/tbo-smart-api/`.

### Me and home

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_me` | – | `Me`: user, full_name, image, roles, is_agent, is_manager, `can` {team, projects_health, sla_summary, escalations, approvals}, departments, teams, `capabilities` (below) | Any agent. `is_manager` = sees the overview (Project Manager role, admins, project leads). Fixture `get_me.json` |
| `get_home` | – | `HomeCounts` | Any agent; counts from My Work and Home's day. Fixture `get_home.json` |
| `get_home_bundle` | – | `{me, counts, tasks}` (tasks = first page of `get_tasks`) | **Call this at launch**: one round trip. Fixture `get_home_bundle.json` |
| `get_action_plan` POST | `refresh` (bool) | `{steps: [{id, text, detail, route}], generated_at, source: "ai"\|"rules", stale, reason}` | Call right after `get_home_bundle` (it reuses the day that call built). The AI may take seconds; `refresh` is rate limited by the hub. Fixture `get_action_plan.json` |

`HomeCounts`: `open_tickets`, `awaiting_reply`, `tasks_open`, `tasks_due_today`,
`tasks_overdue`, `tasks_on_hold`, `tasks_in_review`, `escalated_to_head` (own tasks at L2+),
`approvals` (tasks waiting for my review), `unread_notifications`.

### Capabilities

`Me.capabilities` (in `get_me` and `get_home_bundle`) is the **one** answer to "what does the
app show this person": tabs and actions appear only from these flags. It is computed on the
hub from the user's real roles and project powers (`capabilities()` in `mobile.py`), each flag
with the same check the hub enforces, so the app never decides access itself. A flag says
what to *show*; every endpoint still checks permissions on its own.

| Flag | Type | Granted by | Rule (code) |
| --- | --- | --- | --- |
| `tickets` | bool | System Manager, Agent Manager, ERP Employee (not DM Employees, not content-only people) | `content_team.can_work_tickets` |
| `content` | bool | Admins, Project Managers, DM Coordinators, and the content calendar roles (Content Team, Digital Marketing Head, DM Employee); never ERP Employees | `content_team.in_content_team` |
| `manage_team` | bool | System Manager, Agent Manager, or a head of any active department (Settings → Departments → Heads, or a role in `DEPARTMENT_HEADS` such as Digital Marketing Head for Digital) | `tasky.permissions.can_manage_team` |
| `approve_reviews` | bool | A project's manager (its creator, or a member with the Project Manager project role), its lead, or a Project Coordinator on it | `_review_projects` (the same as `get_approvals`) |
| `scoreboard` | bool | Every agent: the Scoreboard is open to all | `agent_only` |
| `admin` | bool | System Manager, Agent Manager (sees and manages everything) | `tasky.permissions.is_tasky_admin` |
| `departments_headed` | list | The active departments the user heads | `tasky.permissions.departments_headed` |
| `projects_managed` | list | The open projects the user manages or leads (`can_manage_project`); admins manage every project, which `admin` says | `get_managed_projects` + `get_led_projects` |

`manage_team` is **insights only**: it opens `get_insights` and gives no write power. The
nudge and reassign actions keep their own checks (admins, or the project's manager, lead or
coordinator for its tasks); the app shows them only behind `manage_team` and an explicit tap.

### Tasks

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_tasks` | `group?` (overdue, today, upcoming, on_hold, in_review), `cursor`, `limit` | page of `Task` (no description/activity) | My own open tasks only (My Work), overdue first. Like My Work, it reads at most 300 open tasks (`work.LIST_LIMIT`), so the app and the web always show the same list. Fixture `get_tasks.json` |
| `get_task` | `task` | `Task` + `description` (HTML), `activity`, `pull_requests`, `quality` (below) | Anyone who may read the task (#94 visibility: members only their own, leads/coordinators/managers the project's). Fixture `get_task.json` |
| `start_task` POST | `task` | `Task` detail | Starts an Open task (status Working, timer running) or resumes a paused timer. Write permission. Fixture `task_action.json` |
| `pause_task` POST | `task` | `Task` detail | Banks the time; stays Working |
| `complete_task` POST | `task`, `hours_worked` (>0, ≤24), `notes` (required) | `Task` detail | Logs a timesheet on today; a review project moves it to Pending Review. (The web app can also send `days`, hours per day; see workspace-pages.md "Hours by day".) |
| `hold_task` POST | `task`, `reason`, `note?` | `Task` detail | `reason` is one of the hub's: `Laptop / system issue`, `Leave`, `Waiting on customer`, `Waiting on another task`, `Other` |
| `resume_task` POST | `task`, `extend_due_date` (default true) | `Task` detail | The days on hold are added to the due date |
| `hand_over_task` POST | `task`, `teammate`, `reason` (required) | `{task, handed_to}` | The assignee (or the project's lead/coordinator). The task may leave the user's view, so no detail comes back. Fixture `hand_over_task.json` |
| `request_help` POST | `task`, `teammate`, `task_name` (required), `description?`, `due_date?` | `{task, help_task}` | The teammate gets a new task; this one waits on it. Fixture `request_help.json` |
| `review_task` POST | `task`, `approve` (bool), `note` (required when sending back), `rating?` (with approve: `Needs rework`, `Good`, `Excellent`) | `Task` detail | The project's manager, lead or coordinator only. A rating is refused (403) when the reviewer is also an assignee |
| `rate_task` POST | `task`, `rating?` (`Needs rework`, `Good`, `Excellent`; empty clears it) | `Task` detail | A completed task's optional quality rating: whoever assigned it, the project's managers, lead and coordinators, its department's heads and admins; never an assignee (403). `quality.can_rate` says whether to show the control |
| `add_task_comment` POST | `task`, `content` | one activity item | Anyone who can read the task. Fixture `add_task_comment.json` |
| `get_teammates` | `task?` | `[{user, full_name, image, on_leave}]` | Active agents; for a task, its project team unless the user manages the project. Fixture `get_teammates.json` |
| `get_focus` | `limit` (1–3, default 3) | `[Task + focus]` | The 1–3 tasks to do now, in Home's order: `close_first` (overdue, due today, key work in progress), then `in_progress`, `coming_up` (next 7 days) and `no_date`; held and in-review work waits on others and is left out. `focus` names the section. Fixture `get_focus.json` |
| `quick_add_task` POST | `project`, `subject`, `due_date?`, `assignee?` (default: the user) | `Task` detail | `tasky.add_task`, so `can_add_tasks` applies: anyone on the project (or with a task in it) may add; giving it to someone outside the team is the manager's or lead's call. Fixture `quick_add_task.json` |
| `snooze_follow_up` POST | `item` (`Task:TASK-…` or `HD Ticket:123`), `until` (date, tomorrow to 7 days ahead), `reason` (required, ≤500) | `{item, until, reason, level}` | The **assignee** acknowledges today's L0/L1 reminder: their own notices and digest lines about it stop until `until` (reminders start again that day), the reason is noted on the item and today's notice is marked read. Refused while the item is at L2+ or its SLA is breached; those always go out. See [follow-ups.md](follow-ups.md#snooze). Fixture `snooze_follow_up.json` |
| `get_content_tasks` | `start`, `end` (dates, at most 62 days apart), `customer?`, `channel?`, `status?` (a post status; Cancelled posts are left out otherwise), `person?` (tasks assigned to them) | `ContentTasks` | The content calendar's Tasks view (`helpdesk.api.content_tasks`): the role tasks of the posts going live between the dates. Content writers, designers and marketers get their own tasks, the content leads every content task (#94 visibility); outside the content team (`capabilities.content` false, ERP Employees included) 403. Not paged: 1,000 posts and tasks at most (`truncated`). Take steps with `start_task`, `pause_task`, `complete_task`, `hold_task`, `resume_task` and `review_task`, as `actions` allows. Fixture `get_content_tasks.json` |
| `get_my_stats` | `period` (today, week, month, quarter, half, year) | `{period, current, previous, trend}` | The user's own Scoreboard line for this period and the 7 before it, oldest first: `done`, `weighted_work`, `on_time`, `dated`, `on_time_pct`, `key`, `hours`, `score` (`score()`), and `overdue` (now; null for past periods). Past periods are scored without "Overdue now", which is today's state. Fixture `get_my_stats.json` |

`Task`: `name`, `subject`, `project`, `project_name`, `customer`, `status` (Open, Working,
Pending Review, On Hold, Completed, Cancelled), `group`, `exp_end_date`, `is_overdue` (the
hub's rule: past due, or due today and past its estimate; a held task is never overdue),
`is_key`, `is_milestone`, `priority`, `assignees`, `assigned_by` {user, full_name},
`hold_reason`, `hold_note`, `hold_days`, `escalation` {level, label} or null, `timer`
{state: running|paused|idle, started_at, logged_hours}, `expected_hours`, `waiting_on`,
`risks` (sentences), `can_approve`.

`ContentTasks`: `sees_all` (a content lead, who gets every content task), `can_edit` (may
reassign parts), `tasks`, `counts` {todo, in_progress, review, on_hold, done}, `posts`
{name: ContentTaskPost}, `truncated`. A content task: `name`, `subject`, `status`, `stage`
(todo, in_progress, review, on_hold, done), `review_label` (in review: "the lead's review",
"the client's approval", …), `role` (writer, designer, video_editor, marketer, or null for the
post's shared task), `role_label`, `post`, `publish_on`, `project`, `project_name`,
`assignees`, `assignee_names` {user: full name}, `mine`, `due`, `is_overdue`, `hold_reason`,
`hold_note`, `hold_by_name`, `hold_days`, `custom_timer_start` (site time, null while paused),
`custom_timer_elapsed` (banked hours), `estimated_hours`, `escalation_level`, `waiting_on`
(the open task it depends on) and `actions` (start, pause, resume_timer, complete, hold,
resume, approve, reassign: what the viewer may do now). A `ContentTaskPost` is the calendar
post (`name`, `title`, `customer`, `status`, `publish_on`, `channel`, `platforms`, `format`,
`special_day`, the role fields and their hours) with `is_missed` and `progress` {parts, done,
waiting_on: {kind: "review", label} or {kind: "part", role, label, people, task, task_status,
due} or null}. Rules in [content-calendar.md](content-calendar.md#tasks-view).

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
| `comment_ticket` POST | `ticket`, `message` | `Ticket` detail | Write permission. Internal note (`HD Ticket.new_comment`). `message` is plain text, so v1 notes don't support @mentions (the web's mentions are editor markup) and take no attachments (`new_comment` types them as strings but reads them as objects). 60/min per IP |
| `set_ticket_status` POST | `ticket`, `status` | `Ticket` detail | Write permission; `status` must be one of the enabled HD Ticket Statuses (`statuses` in `get_ticket`) |
| `assign_ticket` POST | `ticket`, `agent` | `Ticket` detail | Write permission; `agent` must be an HD Agent. Replaces the current assignees |

`Ticket`: `name` (string), `subject`, `customer`, `contact`, `raised_by`, `priority`, `status`,
`status_category` (Open = waiting on us, Paused = waiting on the customer or a task),
`sla_due`, `sla_kind` (first_response until the first reply, then resolution), `sla_breached`,
`sla_due_soon` (within 4 hours), `assigned_to` (user id), `assignees` [{user, full_name}],
`team`, `opened_at`, `awaiting_reply`, `escalation_level`. The detail (`get_ticket` and the
ticket actions) also has `customer_owner` (`{user, full_name}`, or null when the ticket has no
customer or its customer no ticket owner): who the customer's new tickets go to (see
[ticket-owners.md](ticket-owners.md)); the list rows don't carry it.

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
| `get_in_progress` | `group_by` (project, person, department; default project), `department?`, `customer?`, `person?`, `only_overdue` (bool), `hide_on_hold` (bool) | `InProgress` | **Every agent**, not only managers: the web's In progress page (`helpdesk.api.in_progress`). Tasks follow #94 (people who run a project get its tasks, everyone else their own); posts only for the content team, and outside the content leads only the posts they're on. Not paged: one lane list, tasks capped at 1000 and posts at 500 (`truncated`). Fixture `get_in_progress.json` |
| `get_escalations` | `cursor`, `limit` | page of `Escalation` (L2+, highest level and longest wait first) | System and Agent Managers, like Overview → Follow-ups. Fixture `get_escalations.json` |
| `nudge` POST | `doctype` (Task, HD Ticket), `name`, `message` (≤500) | `{notified}` | Admins for anything; a project's manager, lead or coordinator for its tasks. The owners get a Reminder (bell, chat or email, push) and the item gets a note. Fixture `nudge.json` |
| `reassign` POST | `doctype`, `name`, `to`, `reason` (required for tasks) | as `hand_over_task` / `assign_ticket` | Tasks go through `hand_over_task` (the lead or coordinator hands over the whole task); tickets through `assign_ticket` |
| `get_approvals` | – | `[Approval]` (kind review) | Managers, leads and coordinators of projects; others get 403. Decide with `review_task`. Fixture `get_approvals.json` |
| `get_projects_health` | – | `[ProjectHealth]` | Same as `get_team` (the portfolio). Fixture `get_projects_health.json` |
| `get_sla_summary` | – | `{open, new_today, breached, first_reply_overdue, breaching_soon, unassigned, waiting_on_customer, oldest_unassigned}` | Same as `get_team`. Fixture `get_sla_summary.json` |
| `get_scoreboard` | `period` (today, week, month, quarter, half, year), `department?` or `group?` (a main department with its sub-departments, e.g. `ERP`), `day?` (a past day: its period; a future day is refused) | `{period, period_label, range, department, group, groups, closed, champion, previous_champion, months, me, leaders (top 10), departments}` | Every agent (the Scoreboard is open to all). Weeks are clipped to their month and every month starts on the 1st ([team-dashboard.md](team-dashboard.md#periods)). A closed period's `champion` is the one stored when it closed (`stored: true`); `previous_champion` is the period before's stored champion (e.g. last month's), with `start`, `end` and `reasons`; `months` (year only) is the twelve months side by side (`month`, `future`, `tasks`, `weight`, `on_time_pct`, `quality`, `champion`). Lines carry `weighted_work` next to `tasks_done`; `groups` is `[{group, departments}]`; `departments` rows have `kind` (`group` or `department`), `parent` (a department's group) and `weighted_work`, a group row first with its departments under it. Fixture `get_scoreboard.json` |

`Task.quality` (from `get_task`): `{weight, weight_reasons, quality, quality_reasons, rating,
rated_by, rated_by_name, rated_on, can_rate, self_made}`, e.g. `weight 3.25` with
`["key", "8h estimate", "High priority"]` and `quality 1.25` with `["rated Excellent"]`. The
formulas are in [team-dashboard.md](team-dashboard.md#weight-and-quality).

`TeamMember`: `user`, `full_name`, `image`, `on_leave`, `leave` {to_date, half_day},
`open_tasks`, `working`, `in_review`, `on_hold`, `overdue`, `due_this_week`, `done_this_week`,
`tickets`, `sla_breached`, `working_on`, `next_due`.

`InProgress`: `scope` ("team" or "own"), `group_by`, `summary` (`InProgressCounts`, over the
whole view before `only_overdue` and `hide_on_hold`), `lanes`, `truncated`. A lane is `{key,
kind (project, person, department, content), title, subtitle (the project's customer), tasks,
posts, counts}`. `InProgressCounts`: `in_progress` (Working), `review`, `on_hold`, `overdue`,
`escalated`, `posts`, `missed`, `at_risk`. A task is the web's work item (`name`, `title`,
`project`, `project_name`, `customer`, `department`, `status`, `deadline`, `is_overdue`,
`is_key`, `escalation_level`, `hold_reason`, `hold_note`, `hold_by_name`, `hold_days`,
`waiting_on`, `risks`, `assignees`, `assignee_names` {user: full name}) plus the timer fields
`custom_timer_start` (site time, or null while paused) and `custom_timer_elapsed` (banked
hours) and `estimated_hours`. A post is `{name, title, customer, status, publish_on,
platforms, format, pending: [{role, label, people: [{user, full_name}], task, task_status,
due}], waiting_on ("Client approval", …, or null), is_missed, at_risk}`. Rules in
[workspace-pages.md](workspace-pages.md#in-progress-in-progress).

`Escalation`: `id` (`Task:TASK-…`), `kind` (task, ticket), `doctype`, `ref`, `title`, `owners`,
`level`, `level_label`, `days`, `severity`, `reason`, `route`, `app_route`.

### Stand-up

The async daily stand-up ([standup.md](standup.md)), as on `/helpdesk/standup`. The app opens
it from the "Your stand-up is ready" notification (`reference_doctype` HD Standup).

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_my_standup` | `date?` (YYYY-MM-DD, default today) | `MyStandup` | Any agent, their own. Today without a stored stand-up: a fresh draft from their work, `standup.name` null, not saved until `save_standup`. A future date is refused. Fixture `get_my_standup.json` |
| `save_standup` POST | `values` (JSON: `yesterday`, `today`, `blockers` as rows, `notes` {yesterday, today}, `needs_help`; a section left out stays) | `MyStandup` | Today only, while the stand-up is on. Linked rows can only be kept or removed; a row without `reference_name` is text (≤300 chars). Status unchanged. Fixture `save_standup.json` |
| `submit_standup` POST | `values?` as above | `MyStandup` with status Submitted | Same; may be sent again to update. Fixture `save_standup.json` |
| `get_team_standup` | `team?` (a department; `__none__` for none), `date?` | `TeamStandup` | Heads, leads, coordinators and managers of the department (per the settings) get `can_lead: true` with `plan_vs_done` and `on_leave`; a member gets their own department read-only; any other department is 403. `content_today` for departments with content work (null otherwise, and for viewers outside the content team). Fixtures `get_team_standup.json` (ERP), `get_team_standup_digital.json` (content) |

`MyStandup`: `enabled`, `date`, `previous_day` (the previous working day, "yesterday"),
`is_working_day`, `editable`, `post_at` ("10:30"), `posted`, `teams` (departments the user
leads), `department`, `standup` (`Standup` or null).

`Standup`: `name`, `user`, `full_name`, `date`, `department`, `status` (Draft, Submitted,
Auto-posted), `submitted_on`, `needs_help`, `hours` (null when hidden), `yesterday`, `today`,
`blockers` (`[StandupItem]`), `notes` {yesterday, today}; in a team view for leads also
`plan_vs_done` {planned, done, unplanned} or null.

`StandupItem`: `id` (row id, null before saving), `kind` (task, ticket, post, plan, note),
`title`, `detail`, `reference_doctype`, `reference_name`, `project`, `auto`, `route` (web),
`app_route`, `helper`, `helper_name`, `help_task`, `content` (`StandupContent` or null).

`StandupContent`, on content calendar lines (the content team's role parts and posts,
[standup.md](standup.md#content-calendar)): `post` (HD Content Post name), `part` (writer,
designer, video_editor, marketer; null on a post's own line), `part_label` ("Designer"),
`client`, `go_live` ("YYYY-MM-DD HH:MM:SS"), `stage` (the post's status when the line was
filled in). A part's line is a Task (`app_route` `/task/…`); a post's line has
`reference_doctype` HD Content Post and no `app_route` (the app has no post screen yet: show
`content` inline). Outside the content team, content lines are left out of a team view.

`TeamStandup`: `team`, `teams`, `can_lead`, `date`, `previous_day`, `editable`, `post_at`,
`posted`, `people` (`[Standup]`), `blockers` (`StandupItem` plus `standup`, `user`,
`full_name`, `needs_help`), `needs_help` (names), `counts` {people, submitted, pending, auto,
blockers}, `on_leave` ([{user, full_name, to_date, half_day}]), `content_today`
(`[ContentTodayPost]` or null). The team's actions (nudge, assign help, create a task) are
web-only for now: `helpdesk.api.standup`.

`ContentTodayPost`: `post`, `title`, `client`, `go_live`, `channels` (list), `stage` (status),
`state` (`missed`, `at_risk` = going live today without approval, `published`, `ready`),
`people` ([{user, full_name}] on its team), `route` (web). Missed first, then at risk, then by
time; posts going live that day plus the department's posts missed in the week before.

### Compete (Scoreboard for the app)

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_competition` | `period` (today, week, month, quarter, half, year; default week), `limit` (1–50, default 10), `day?` (a past day: that period's boards) | `Competition` | Every agent. The boards are public, as on the web Scoreboard: every active department, past the DM/ERP department walls (`viewer_access`). Streaks, bests, badges and `move_up` are the user's own. Fixture `get_competition.json` |

Everything is derived from the Scoreboard (`helpdesk.team_dashboard`: `collect`, `tally`,
`rank`, `score()`) and the tasks' due dates; **there is no second scoring formula**
(`helpdesk/competition.py`).

`Competition`:

- `period`, `period_label`, `range` {start, end}, `compare` {start, end}: the comparison is
  the previous period **up to the same point** (`comparison_bounds`), as the web tiles.
- `closed` (a past period picked with `day`: its boards' champions are the stored ones and
  `move_up` is null) and `previous_champion` (the period before's stored whole-team champion,
  or null).
- `me`: the user's line on the whole team's board (below), or null.
- `team`, `groups` (one per department group, e.g. ERP with GrowthX and Internal / R&D) and
  `departments` (one per active department): `{department, group, champion (user or
  null), of (people on the board), leaders (top `limit`), me}`. A board line is `{user,
  full_name, image, department, rank, score, rank_delta, is_champion, tasks_done,
  weighted_work, on_time_pct, overdue}`. Boards rank exactly as the web People view (`ranked_people`,
  `people_rows`): whoever has work in the scope, then its members with nothing.
- **`rank_delta`**: the rank in the comparison period minus the rank now (`+2` = up two).
  The previous rank is among the people who delivered something then (`delivered`: tasks
  done plus posts published), so ranks among people with nothing (which only follow the
  alphabet) never show as movement; anyone else has `rank_delta: null` ("new"). The
  comparison is scored without "Overdue now", which is today's state.
- `streaks`: `{on_time_days, best_on_time_days, podium_weeks, lookback_days}`, see below.
- `personal_bests`: `{most_on_time_in_a_week, most_done_in_a_week, most_key_in_a_week}`
  (each `{value, week_start}` or null, over the last 26 weeks), `longest_on_time_streak`
  (working days, within the streak's look-back), `champion_titles` (HD Team Champion
  records of weeks and longer, any department), `weeks_looked_at`.
- `badges`: `{earned: [{name, badge, label, period_type, start, end, department, detail,
  earned_on}] (latest 20), catalog: [{badge, label, rule, count}]}`.
- `challenge`: the weekly challenge (below), or null when it's off.
- `move_up`: `{leader, next {user, full_name, score} or null, gap, actions}`. `gap` is the
  score of the person ranked just above minus the user's (ties go to the better on-time
  rate). `actions` are up to 3 of the user's own open tasks (not held, not in review) that
  gain the most: each is `score()` with the task finished now minus `score()` as it is, so
  it follows the formula exactly, e.g. `{task, subject, due, points: 1.5, passes, text:
  "Finish “TBO ERP: migrate customers” on time: +1.5"}`. On time when its due date is today
  or later; an overdue task also stops costing its `−1` ("Finish overdue …"); one without a
  due date earns half ("no due date, so half credit"). The task counts by its weight
  (`task_weight`: key, estimate, priority; one the user gave themselves counts half) and,
  since it isn't rated yet, quality 1. `passes` says it alone would close the gap.

**Streaks** respect the working calendar: HD Work Settings' weekly off and Saturdays off and
the default SLA's holidays (`recurrence.working_day_checker`).

- **On-time streak** (`on_time_days`): working days in a row, back to today, on which
  everything the user had due was done on time (Completed on or before its due date). A
  working day with nothing due neither counts nor breaks it; something late breaks it.
  Work held or in review waits on someone else and is left out (as "Overdue now" does). A
  task due on a day off counts on the next working day. Today counts once all of it is done,
  and its pending work doesn't break the streak until the day is over. Looks back 90 days.
- **Department top 3** (`podium_weeks`): closed weeks in a row, up to last week, with the
  *Department top 3* badge.

**Badges** (`HD Badge Award`: user, badge, period type/start/end, department, detail,
earned_on). Awarded by the daily 00:30 job that closes periods
(`team_dashboard.close_period` → `competition.award_badges`), after the champions. The
record name comes from the badge, person, period and department, so a re-run awards and
tells nobody twice, and the history never shifts. Each new badge is told once through
`notify_users` ("You earned “Key task closer”: 3 key tasks or milestones done on time in
the week"), except the champion badges: the champion already heard "You're the …
champion".

| Badge | Label | Rule | When |
| --- | --- | --- | --- |
| `on_time_streak` | On-time streak 5 | The on-time streak reaches 5 working days (a new streak can earn it again) | Each day's close |
| `key_closer` | Key task closer | 2 or more key tasks or milestones completed on time in the week | Week close |
| `zero_overdue_week` | Zero overdue week | At least 3 tasks due in the week, every one done on time, and nothing overdue when the week closed | Week close |
| `podium` | Department top 3 | Top 3 of a department's week by `score()`, among people with the week's minimum activity (as the champion) | Week close |
| `champion_week` | Champion of the week | The week's champion of the whole team or a department (HD Team Champion) | Week close |
| `champion_month` | Champion of the month | The month's champion of the whole team or a department | Month close |

HD Badge Award: System Manager full, Agent Manager read; agents read their own through
`get_competition`.

**Weekly challenge**: one goal for the whole team each week (Monday to Sunday), set in
**Settings → Follow-ups → Weekly challenge** (`HD Follow Up Settings.weekly_challenge`):

| Setting | Goal shown | Counts |
| --- | --- | --- |
| *Key tasks due this week* (**default**) | Close every key task due this week | Key tasks and milestones due this week |
| *Every task due this week* | Finish every task due this week on time | Every task due this week |
| *Off* | – | `challenge` is null |

`challenge`: `{key, title, week {start, end}, goal (tasks counted), done (completed on time),
pct, complete, mine {done, total} or null, completed_by [{user, full_name, image}]}`.
`completed_by` is everyone with tasks in the challenge who finished all of theirs on time.
Cancelled tasks don't count; held and in-review ones count as not done yet.

### Repeat issues (Scoreboard)

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_repeat_issues` | `period` (today, week, month, quarter, half, year; default week), `department?` | `RepeatIssues` | Every agent, as on the web Scoreboard: every active department, past the DM/ERP department walls; an inactive department is refused. **Read-only**: the actions (root-cause task, KB draft, "Not a repeat") stay on the web for now; `access` says which ones the user could take there. Fixture `get_repeat_issues.json` |

The web's own answer (`helpdesk.api.repeat_issues.get_repeat_issues`), unchanged; the rules
are in [team-dashboard.md](team-dashboard.md#repeat-issues).

- `period` `{key, start, end, lookback_start}`, `rules` `{lookback_days, min_occurrences,
  min_in_period}`, `department`, `access` `{can_act, can_draft_kb}`.
- `summary`: `{issues, customers, rising, tickets_in_period, tasks_in_period}`.
- `customers`: by repeat volume this period, each `{customer, issues, in_period, total,
  rising, projects (open: {name, project_name, department}), clusters}`.
- A cluster: `{id, customer, title, title_source ("ai" | "subjects"), cause, fix, subject,
  tickets, tasks, in_period, earlier, total, first_seen, last_seen, trend ("rising" |
  "steady"), kinds [{label, count}], people [{user, name, count}], avg_resolution_hours,
  departments, items, root_cause, article}`. `items` are newest first: `{kind (ticket, task),
  doctype, name, subject, date, status, project, in_period}`. `root_cause` is `{issue, task,
  subject, status, project}` or null; `article` `{name, title, status}` or null. `cause` and
  `fix` are null without AI.

### Insights (management, read-only)

| Method | Params | Returns | Who / notes |
| --- | --- | --- | --- |
| `get_insights` | `period` (default week), `department?` | `Insights` | `manage_team` only. Admins: every department (no `department`) or the one asked for. Department heads: the departments they head, or one of them; another department is refused (403). Everyone else gets 403. **No write actions.** Fixture `get_insights.json` |

`helpdesk/team_insights.py`, from what the hub already counts:

- `scope`: `{departments (null = the whole team), label, tickets}`. Tasks are in scope by
  their project's department; tickets belong to the support department (Settings →
  Follow-ups), so their figures are null when the scope doesn't include it.
- `tiles`: `[{key, label, value, previous, delta, unit, better}]`, `better` being the good
  direction ("up", "down"; null for state and for hours, which aren't judged):
  `tasks_done`, `on_time_pct` (as the Scoreboard counts them), `overdue_now` (no previous:
  today's state), `escalations_open` (L2+ follow-ups in scope, `follow_ups.escalations`),
  `sla_breaches` (tickets opened in the period whose SLA failed), `first_response_median`
  (minutes, tickets first answered in the period), `hours_logged`. Previous = the
  comparison period up to the same point.
- `trend`: the last 8 periods, this one included: `{start, end, label, throughput (tasks
  done), on_time_pct, overdue}`. A past period's `overdue` is the tasks past their due date
  at its end and not completed by then; past holds aren't recorded, so work held or in
  review now is left out, as "Overdue now" does.
- `risks`: `projects` (top 5 open projects by overdue tasks, then milestones whose due date
  moved or passed: `{project, project_name, department, overdue, slipped_milestones}`),
  `people` (top 5 by overdue plus escalated work, **names and counts only**: `{user,
  full_name, overdue, escalated}`), `tickets_breaching_soon` (top 5 open tickets whose SLA
  runs out within `breaching_within_hours` (4): `{ticket, subject, due, kind, assignees}`),
  `tickets_breaching_count`.
- `workload`: `{people: [{user, full_name, image, open_tasks, overdue, utilisation?, load?,
  free_hours?}] (busiest 15), average_open, capacity}`. The capacity fields come from
  capacity planning (`api/capacity.get_capacity`, next week) for people who plan capacity
  (project managers, leads, admins); `capacity` says whether they're there.
- `summary`: `{source: "ai" | "rules", bullets (3–5), reason, generated_at?}`. Written by
  the hub's AI (`ai_engine.call_haiku`) from the tiles and risks only, never hours; any
  bullet with a number that isn't in the facts is dropped (`home_plan.clean_steps`, the
  Scoreboard's guard). Cached 12 hours per period and scope; after a failure the rules are
  used for 15 minutes. When AI is off or fails, and always for Today (as the Scoreboard
  writes no analysis for a day), the same facts come as plain sentences.

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
| `Ticket` | `assigned_to` is a user id, not a full name (the mocks compare with `full_name`); adds `assignees`, `status_category`, `sla_kind`, `sla_breached`, `sla_due_soon`; `conversation` and `customer_owner` only in the detail | app (additive) |
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
| `Scoreboard` | `range` is `{start, end}`; `champion` is the dashboard's card (`name`, `score`, `reasons`, `breakdown`); `get_scoreboard` has no rank change: use `get_competition` (`rank_delta`); breakdown items are `{key, points, detail}` | app |

## Owner setup checklist

1. Create the **OAuth Client** above and send its Client ID to the app developer.
2. For one login across both sites, do "Single sign-in with Microsoft → Owner setup".
3. Turn on **Settings → General → Mobile app → Mobile push** once the app ships with push.
4. Pick the **weekly challenge** in Settings → Follow-ups (default: close every key task due
   this week), and set each department's **Heads** in Settings → Departments: heads get
   `manage_team` and the insights of their departments.
5. Nothing else: the doctypes (HD Mobile Device, HD Badge Award, HD Follow Up Snooze) and the
   settings arrive with `bench migrate`; badges start with the next period close.

# TBO Chat sign-in with Microsoft

TBO Chat is self-hosted Chatwoot Community (v4.18) at `https://chat.teambackoffice.com`.
The owner's rule: **Microsoft is the only sign-in, and ending a Microsoft account ends all
access.** Chatwoot Community has no Microsoft (Entra) or SAML sign-in (SAML is Enterprise
only; Google is its only social login). TBO Support (the hub) already signs staff in with
Microsoft, so the hub brokers TBO Chat sign-in through Chatwoot's **Platform API**.

Code: `helpdesk/chatwoot_sso.py` (logic), `helpdesk/api/chatwoot_sso.py` (the entry point, the signed-out page and
the settings API), `ChatwootClient.platform_request` in `helpdesk/chatwoot_bridge.py`,
`desk/src/components/Settings/Chat/TboChatSettings.vue` (Settings → TBO Chat) and
`desk/src/composables/useTboChat.ts` (Open TBO Chat in the profile menu). Tests:
`helpdesk/tests/test_chatwoot_sso.py`.

## Flow

```
Agent clicks Open TBO Chat (or goes to chat.teambackoffice.com/app/login)
  → Caddy sends /app/login to GET teams.teambackoffice.com/api/method/helpdesk.api.chatwoot_sso.login
  → not signed in to the hub: /login?redirect-to=<that path> → Login with Office 365 → back
  → hub: sign-in on? active HD Agent? under the rate limit?
  → GET  /api/v1/accounts/{id}/agents                 (bridge user token)  find by email
  → POST /platform/api/v1/users {name,email,password} (platform token)     find or create
  → POST /platform/api/v1/accounts/{id}/account_users {user_id, role}      only when missing
  → GET  /platform/api/v1/users/{user_id}/login → {"url": ".../app/login?email=…&sso_auth_token=…"}
  → 302 to that url → Chatwoot's login page posts {email, sso_auth_token} to POST /auth/sign_in
```

### `GET /api/method/helpdesk.api.chatwoot_sso.login`

- **Guest:** redirected to `/login?redirect-to=%2Fapi%2Fmethod%2Fhelpdesk.api.chatwoot_sso.login`.
  Hub sign-in is Microsoft (Login with Office 365), which keeps `redirect-to`. Password sign-in
  on the hub should be off (System Settings → Disable Username/Password Login, and Login with
  Email Link off), keeping one break-glass Administrator; that is on the owner's list.
- **Sign-in off** (`sso_enabled` unset): a 404 page, "TBO Chat sign-in is off".
- **Not an active agent** (no HD Agent with `is_active`): a 403 page, "TBO Chat is for agents".
- **Rate limit:** 5 sign-ins per person per 60 seconds (Redis key `chatwoot-sso:<user>`; the
  expiry is set again if it was ever lost),
  then a 429 page. It also ends a loop: when Chatwoot rejects a one-time link, its page sends
  the browser back to `/app/login`, which Caddy sends back here.
- **Finding the person:** by the hub User's email (lowercase) in the account's agents list,
  read with the bridge user's token. Chatwoot's Platform API has no search by email.
- **Missing person:** with **Add agents who aren't in TBO Chat yet** (`sso_create_users`, on by
  default) they are created and added to the account with **Role for new agents**
  (`sso_default_role`, `agent`), or `administrator` for System Managers and Agent Managers when
  **Managers join as administrators** (`sso_managers_as_admins`, on). Off: a 403 page, "You're
  not in TBO Chat yet". A new agent sees no inbox until a Chatwoot administrator adds them to
  one; administrators see all.
- **Existing members keep their role:** `account_users` create is find-or-update in Chatwoot,
  so the hub never calls it for someone already in the account.
- **Password:** Chatwoot requires one when creating a user. The hub sends a random 43+ character
  password (with the upper, lower, digit and symbol Chatwoot asks for) that is never stored or
  shown, so nobody knows it.
- **Signed out of TBO Chat:** with `signed_out=1`, or when the request comes from TBO Chat
  (`Referer` host is the Chatwoot URL's host) within 60 seconds of the hub last sending that
  person into TBO Chat, the hub shows "You're signed out of TBO Chat" (200) instead of signing
  in, with **Open TBO Chat again** (the same address with `continue=1`, which always signs in)
  and **Sign out of TBO Support too** (a form POST, with the CSRF token, to
  `helpdesk.api.chatwoot_sso.sign_out`: the hub's own logout, then `/login`). Neither the page
  nor anything stored holds the one-time link. See [Signing out](#signing-out-of-tbo-chat).
- **The one-time link** is followed only when it starts with `<Chatwoot URL>/app/login?`; any
  other answer is a 502 page, "Couldn't open TBO Chat". The link is a credential: it is never
  logged, stored or put in a page. Chatwoot keeps the token in Redis for **5 minutes** and it
  works **once**.

### Signing out of TBO Chat

Chatwoot's **Log out** calls `DELETE /auth/sign_out` and then sets `window.location` to the
installation config `LOGOUT_REDIRECT_LINK` (default `/app/login`; `clearCookiesOnLogout` in
`app/javascript/dashboard/store/utils/api.js`, v4.18.0). With the default, Caddy sent that
`/app/login` to the hub, and the hub signed the person straight back in while their hub
session lasted: logout never stuck.

The `Referer` alone can't tell a sign-out from a first visit. A first visit to
`chat.teambackoffice.com` without a Chatwoot session loads the app, whose router calls
`window.location.assign('/app/login')` (`validateAuthenticateRoutePermission` in
`app/javascript/dashboard/routes/index.js`). Both are full navigations from a Chatwoot page to
`/app/login`, and after Caddy's cross-origin redirect the browser sends the hub only the origin
(`https://chat.teambackoffice.com/`) in both cases.

So the hub uses two signals:

1. **`signed_out=1`, the main one.** Chatwoot's `LOGOUT_REDIRECT_LINK` is set to the hub's entry
   point with this flag (owner step 7), so only a sign-out carries it. Chatwoot also uses that
   link when a stale session is found (`validityCheck` answers 401), so someone whose Chatwoot
   session ran out sees the same page; one click opens TBO Chat again.
2. **Coming back at once, the fallback.** After each successful sign-in the hub keeps a flag
   for 60 seconds (Redis `chatwoot-sso-opened:<user>`; only that it happened, never the link).
   A request from TBO Chat (`Referer` host = the Chatwoot URL's host) while that flag is set is
   a session that ended at once: a sign-out before step 7 is done, or a one-time link Chatwoot
   refused. Either way the page is shown instead of another sign-in, which also breaks any
   redirect loop. Opening TBO Chat from the hub menu, a bookmark or a link (no TBO Chat
   referer) always signs in; so does a first visit to `chat.teambackoffice.com` more than a
   minute after the last sign-in.

`continue=1` skips both. A guest is sent to the hub sign-in as before, whatever the flags.
No Caddy change is needed.

### Why the Platform App can sign in existing users

A Platform App may only manage the users and accounts it created or was granted
(`platform_app_permissibles`). Chatwoot's `POST /platform/api/v1/users` finds an existing user
by email instead of creating a second one, and grants the Platform App that user. So each
existing agent is granted on their first sign-in, with no console step. The **account** is the
exception: it was created during onboarding, so it must be granted once (see owner steps).

## Offboarding

When the hub ends someone's access, TBO Chat follows:

| Event | Hook | Reason logged |
| --- | --- | --- |
| A User is disabled (by hand, or by `helpdesk.offboarding` when the Microsoft account is disabled or gone) | User `on_update` → `chatwoot_sso.on_user_update` | User disabled |
| An HD Agent is deactivated | HD Agent `on_update` → `chatwoot_sso.on_agent_update` | Agent deactivated |
| An HD Agent is deleted | HD Agent `on_trash` → `chatwoot_sso.on_agent_trash` | Agent removed |

When `helpdesk.offboarding` disables someone for leaving Microsoft, its own log row carries the
Microsoft reason; the TBO Chat row says "User disabled". Deleting a User (rather than disabling
it) isn't handled: Frappe keeps Users that have history, and the log links to the User.

`remove_from_chat` runs in the background (queue `short`, after the commit): it finds the person
in the account's agents by email and calls
`DELETE /platform/api/v1/accounts/{id}/account_users {"user_id": …}`. Success writes an **HD
Offboarding Log** row with action **Removed from TBO Chat** (the action of the hub's own
disables is **Disabled in TBO Support**; Settings → General → Offboarding's "Recently disabled"
lists only those). Someone not in the account is left alone. A failure writes an Error Log
titled "TBO Chat: couldn't remove someone", which the hub's error alerts post to the escalation
channel; the person can't sign in again meanwhile, because the hub refuses them.

Removal runs whenever both tokens are saved, even with sign-in switched off. Reactivating the
person lets them sign in again, and they are re-added as a new member (with the role rules
above), without their old inboxes and teams.

### What happens to Chatwoot sessions

Chatwoot (devise_token_auth) keeps sign-in tokens on the user for 2 months. The Platform API
can't revoke them, and Chatwoot has no "blocked" user state. Removing the account membership
is what ends access:

- `AccountUser#destroy` runs `Agents::DestroyJob`: the person leaves every inbox and team of the
  account, their conversations are unassigned (back to the queue) and their notification
  settings go.
- Every account request (`/api/v1/accounts/1/…`) checks the membership on each call
  (`EnsureCurrentAccountHelper#account_accessible_for_user?`), so an open browser tab gets 401
  on its next request; real-time events are sent to account members only.
- Their token still authenticates account-free calls such as `/api/v1/profile`, which show
  nothing of TBO's data. To wipe the tokens too (a hostile leaver), run on the server:
  `cd /opt/chatwoot && sudo docker compose exec -T rails bundle exec rails runner 'User.find_by!(email: "person@teambackoffice.com").update!(tokens: {})'`.
- Turning sign-in on does not end anyone's existing Chatwoot session; those stay valid until
  they sign out or expire. Signing out of Chatwoot ends at the hub's "You're signed out of TBO
  Chat" page, which also offers to sign out of the hub.

## Settings

HD Chatwoot Settings, System Managers only, in **Settings → TBO Chat** (Integrations).

| Setting | Field | Default |
| --- | --- | --- |
| Enabled (header switch) | `sso_enabled` | off |
| Chatwoot URL (shared with the bridge) | `base_url` | `https://chat.teambackoffice.com` |
| Account ID (shared with the bridge) | `account_id` | 1 |
| Bridge User Access Token (shared with the bridge, masked) | `api_access_token` | – |
| Platform App Token (masked, removable) | `platform_api_token` | – |
| Add agents who aren't in TBO Chat yet | `sso_create_users` | on |
| Role for new agents | `sso_default_role` | agent |
| Managers join as administrators | `sso_managers_as_admins` | on |

- The account ID is the bridge's `account_id`, not a second field: sign-in and the bridge must
  use the same Chatwoot account.
- Turning sign-in on without the URL, the account ID or either token fails with "Platform App
  Token: add it before…" (or that field's label), shown under a token field.
- Tokens never go back to the browser; the page sends one only to replace or remove it
  (`helpdesk.api.chatwoot_sso.get_settings` / `save_settings`).
- **Open TBO Chat** appears in the profile menu (desktop and mobile) for active agents while
  sign-in is on (`can_open_chat` from `helpdesk.api.auth.get_user`). It opens the entry point in
  a new tab.

## Server: Caddy on chat.teambackoffice.com

Applied by hand after the hub deploy; the repo doesn't touch the server. Caddy faces the
internet directly, so `remote_ip` is the client's address. The office IP `103.160.194.39` is
the break-glass address.

**Why password sign-in can't be blocked outright:** Chatwoot's one-time link signs in through
the same `POST /auth/sign_in` as a password, with `{email, sso_auth_token}` in the JSON body,
and Caddy can't read a request body. So outside the office, `POST /auth/sign_in` is allowed
only when it comes from the one-time link's page (its `Referer` is
`https://chat.teambackoffice.com/app/login?…sso_auth_token=…`; Chatwoot sends
`Referrer-Policy: strict-origin-when-cross-origin`, so same-origin requests carry the full
address). A script can fake a Referer, so the real guarantee is that nobody knows a Chatwoot
password: users the hub creates get unknown random passwords, password resets are blocked,
and the owner steps rotate the existing agents' passwords. The Chatwoot mobile app signs in
with a password, so it doesn't work for agents any more; they use the web app (installable
as a PWA).

### Caddyfile

Back up first: `sudo cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.pre-sso`. Then add these
lines at the top of the existing `chat.teambackoffice.com { … }` block, keeping its
`/brand/*` handling and `reverse_proxy`:

```caddyfile
	# --- TBO Chat: Microsoft-only sign-in through TBO Support (tbocloud/helpdesk docs/chatwoot-sso.md) ---
	@sso_super_admin {
		path /super_admin /super_admin/*
		not remote_ip 103.160.194.39
	}
	handle @sso_super_admin {
		respond "Not available" 403
	}

	@sso_password_reset {
		path /auth/password /auth/password/*
		not remote_ip 103.160.194.39
	}
	handle @sso_password_reset {
		respond "Password reset is off. Sign in with Microsoft." 403
	}

	@sso_password_sign_in {
		method POST
		path /auth/sign_in
		not remote_ip 103.160.194.39
		not header_regexp Referer ^https://chat\.teambackoffice\.com/app/login\?(.*&)?sso_auth_token=
	}
	handle @sso_password_sign_in {
		respond "Password sign-in is off. Sign in with Microsoft." 403
	}

	@sso_login_page {
		path /app/login /app/login/ /app/auth /app/auth/*
		not query sso_auth_token=*
		not {
			remote_ip 103.160.194.39
			query breakglass=1
		}
	}
	redir @sso_login_page https://teams.teambackoffice.com/api/method/helpdesk.api.chatwoot_sso.login 302
	# --- end TBO Chat sign-in ---
```

The refusals sit in `handle` blocks, not bare `respond` lines: Caddy runs `handle` before
`respond` and `reverse_proxy`, and sorts a `handle` with a matcher before a catch-all one, so
they win whether the proxy is a bare `reverse_proxy` or inside `handle { … }`. `redir` runs
before both.

For reference, the whole site block then reads like this (the `/brand` and proxy lines are
the existing ones; keep the server's exact versions):

```caddyfile
chat.teambackoffice.com {
	# … the TBO Chat sign-in lines above …

	handle_path /brand/* {
		root * /opt/chatwoot/brand
		file_server
	}
	handle {
		reverse_proxy 127.0.0.1:3000
	}
}
```

Everything not matched above is proxied unchanged: `/widget`, `/packs`, `/api/v1/widget`,
`/public`, `/webhooks/*` (WhatsApp/Meta), `/platform/api` (the hub), `/api/v1` (the hub
bridge's token calls), `/cable`, `/rails/active_storage`, `/brand`, `/app/login?…sso_auth_token=…`
(the one-time link's page) and `POST /auth/sign_in` from that page.

**Break glass** (from the office IP only): `https://chat.teambackoffice.com/app/login?breakglass=1`
shows Chatwoot's password form, password reset and `/super_admin` work, and `POST /auth/sign_in`
is open.

Apply and check:

```sh
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
# from outside the office:
curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://chat.teambackoffice.com/app/login          # 302 → teams…chatwoot_sso.login
curl -s -o /dev/null -w '%{http_code}\n' 'https://chat.teambackoffice.com/app/login?email=a&sso_auth_token=x' # 200
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://chat.teambackoffice.com/auth/sign_in \
  -H 'Content-Type: application/json' -d '{"email":"a@b.c","password":"x"}'                                   # 403
curl -s -o /dev/null -w '%{http_code}\n' https://chat.teambackoffice.com/super_admin                           # 403
curl -s -o /dev/null -w '%{http_code}\n' https://chat.teambackoffice.com/api/v1/widget/config                  # not 403
```

Then sign in with **Open TBO Chat** as an agent. If that one-time sign-in is refused (403 on
`/auth/sign_in`), the browser didn't send the Referer: remove the `@sso_password_sign_in`
matcher and its `handle` block, reload, and rely on the password rotation.

### Rollback

```sh
sudo cp /etc/caddy/Caddyfile.pre-sso /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile && sudo systemctl reload caddy
```

and turn **Enabled** off in Settings → TBO Chat. Chatwoot's password form is back; agents whose
password was rotated use "Forgot password" (now allowed again) to set one.

## Owner steps

1. **Create the Platform App** in Chatwoot: `https://chat.teambackoffice.com/super_admin` (from
   the office) → **Platform Apps** → **New platform app**, name `TBO Support sign-in` → save →
   open it and copy its **access token**.
2. **Grant it the account** (once, on the server):
   ```sh
   cd /opt/chatwoot && sudo docker compose exec -T rails bundle exec rails runner \
     'app = PlatformApp.find_by!(name: "TBO Support sign-in"); PlatformAppPermissible.find_or_create_by!(platform_app: app, permissible: Account.find(1)); puts "granted account #{Account.find(1).name}"'
   ```
   (`docker compose ps` shows the service name if it isn't `rails`.)
3. **In TBO Support**, Settings → TBO Chat: check the Chatwoot URL and account ID, make sure the
   Bridge User Access Token is saved, paste the Platform App Token, switch **Enabled** on and
   **Save changes**. The bridge's settings were saved before these fields existed, so on the
   live site **Add agents who aren't in TBO Chat yet** and **Managers join as administrators**
   start off and the role empty (treated as agent): set them here too.
4. **Apply the Caddyfile** above and run its checks.
5. **Rotate the existing passwords** so nobody can use a Chatwoot password (Super Admins, the
   break-glass accounts, are left alone; their `type` is `SuperAdmin`):
   ```sh
   cd /opt/chatwoot && sudo docker compose exec -T rails bundle exec rails runner \
     'n = 0; User.where(type: nil).find_each { |u| u.password = SecureRandom.base58(32) + "aA1!"; u.save!(validate: false); n += 1 }; puts "rotated #{n}"'
   ```
   Chatwoot keeps each person's newest session (`remove_tokens_after_password_reset`) and ends
   the others.
6. Turn off password sign-in on the hub (System Settings), keeping one break-glass
   Administrator.
7. **Send Chatwoot's Log out to the hub's signed-out page** (so logout sticks; see
   [Signing out](#signing-out-of-tbo-chat)):
   ```sh
   cd /opt/chatwoot && sudo docker compose exec -T rails bundle exec rails runner \
     'c = InstallationConfig.find_or_initialize_by(name: "LOGOUT_REDIRECT_LINK"); c.value = "https://teams.teambackoffice.com/api/method/helpdesk.api.chatwoot_sso.login?signed_out=1"; c.locked = false; c.save!; puts GlobalConfig.get_value("LOGOUT_REDIRECT_LINK")'
   ```
   Saving clears Chatwoot's config cache; an open Chatwoot tab picks it up on its next full
   page load. Chatwoot upgrades keep an existing value. To undo, set the value back to
   `/app/login`. Check: sign in with **Open TBO Chat**, click **Log out** in Chatwoot, and the
   hub page "You're signed out of TBO Chat" appears.

## Decisions

- **Hub as broker, not a Chatwoot change:** Community has no Entra/SAML, and patching Chatwoot
  would have to be redone on every upgrade. The Platform API is stable and documented.
- **Lookup with the bridge token:** the Platform API can't search by email, and creating
  through it to look someone up would add users even with adding switched off.
- **Remove from the account, don't delete the user:** deleting a Chatwoot user loses the
  sender of their past messages; removal keeps history and ends access.
- **Own per-user rate limit:** Frappe's `rate_limit` keys on IP or a request argument, and
  answers with JSON; this one keys on the signed-in user and shows a page.
- **Sign-out signal is Chatwoot's `LOGOUT_REDIRECT_LINK`, with a 60-second fallback:** the
  referer can't tell a sign-out from a first visit (see [Signing out](#signing-out-of-tbo-chat)),
  and a Caddy rule can't either, because both are the same navigation to `/app/login`. The
  logout link is a supported Chatwoot setting, so it survives upgrades; the fallback keeps
  logout working (and loops broken) before it is set.
- **Removal is not retried automatically:** a failure goes to the Error Log and the error
  alerts; disabling the person again (or deactivating the agent) retries.

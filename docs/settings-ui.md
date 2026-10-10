# Settings: the page pattern

Every page in the Settings modal (`desk/src/components/Settings/`) is built from the same few
pieces, so the pages look and behave alike: one header, one Save button, the same rows, lists
and states. It follows [ui-guidelines.md](ui-guidelines.md) and
[engineering-guardrails.md](engineering-guardrails.md).

## The modal (`SettingsModal.vue`, `settingsModal.ts`)

- **Sidebar** (from `sm`): groups Account, Email Settings, App Settings, Integrations, each
  with a heading. Pages are buttons in a list; the current one has `aria-current="page"` and
  the app sidebar's active style (`data-slot="sidebar-item"` in `theme.css`: panel surface,
  hairline, brand icon). Up/Down, Home and End move between pages.
- **Small screens**: the sidebar is replaced by one native select (grouped by the same
  headings), so every page stays reachable.
- **Leaving a dirty page**: while a page holds unsaved changes the modal can't be dismissed by
  an outside click, and switching pages asks "Leave without saving?".
- Pages and their role gates live in `tabs` (`settingsModal.ts`); `setActiveSettingsTab(name)`
  opens one by its label. The gates are only for the UI; the server checks permissions.

## Page shell: `layouts/SettingsLayoutBase.vue`

Every page renders inside it. It draws the header with `SettingsLayoutHeader.vue` (the one
settings header) and the scrolling content area.

| Prop / event | What it does |
| --- | --- |
| `title`, `description` | The page name (same as its sidebar label) and one line on what it changes. Slots `title` / `description` replace them when the description needs a link. |
| `badge` slot | A status next to the title, e.g. ERPNext "Not installed". |
| `back-label`, `@back` | A back button for sub-pages (an SLA policy, a team, Twilio…), named e.g. "Back to SLA policies". |
| `dirty` | Shows the **Unsaved** badge and keeps the modal open until saved or left. The page no longer sets `disableSettingModalOutsideClick` itself. |
| `@save`, `saving`, `save-label`, `save-disabled` | Renders the page's one primary button in the header: **Save changes** by default, or an outcome label for new records ("Create policy", "Create team", "Add account"). Disabled until `dirty`; `save-disabled` overrides that (a new record that can be saved as it is, or a form whose required fields aren't set). Shows a spinner while `saving`. Hidden while the page loads or has failed. |
| `header-actions` slot | Secondary header actions before Save: an **Enabled** switch (frappe-ui `Switch` with its `label`), Preview, Pull emails, a ⋯ menu. |
| `header-bottom` slot | Search and filters for list pages. |
| `loading` | A skeleton instead of the content. |
| `error`, `@retry` | "Couldn't load these settings" with the server's message and **Try again**. A `PermissionError` (or HTTP 403) shows "You can't open these settings" instead, with no retry. |

### Save behaviour

- **One Save per page**, in the header, labelled by outcome. Never a floating or footer Save.
- Disabled until something changed; spinner while saving; a success toast says what was saved
  ("CRM settings saved"); a failure toast carries the server's message and the form keeps its
  values so the user can fix and retry.
- Field errors show under the field (`ErrorMessage role="alert"`), saying what to fix.
- **Exceptions kept from upstream:** on General, the six switches in `toggleFields` and
  "Disable signup" save as soon as they change; list rows' Enabled switches (SLA, assignment
  rules, field dependencies) and Departments' actions save straight away, each with a toast.
- Sub-pages ask "Leave without saving?" before going back with unsaved changes.

## Form pieces

- **`SettingsSection.vue`**: a titled group of settings (title, optional description and
  `actions` slot). Sections in one parent are separated by a hairline; the first has none.
  Replaces the old `<hr class="my-8">` + heading markup.
- **`SettingRow.vue`**: one setting with its label and help text on the left and the control
  on the right; stacked on small screens. Every control must be named by the visible label:
  its slot gives `id` and `labelledby`. Controls that take an id (Switch, FormControl, frappe-ui
  Select such as `AvailabilityMenu`) bind `:id="id"`. Popover triggers (`SelectDropdown`,
  `Link`, both `Autocomplete`s) take `:id="id" :labelledby="labelledby"`, so the trigger is
  named by the label plus its current value. A Button with its own text needs neither.
- **`ChipListInput.vue`**: picked records as removable chips plus a Link picker to add more
  (File storage's document types, Content's alert recipients).
- Plain fields use frappe-ui `FormControl` with `label` (above the field) and `description`.
- The large upstream editors (SLA policy, holiday schedule, assignment rule) keep their own
  layout, with section headings and dividers matched to `SettingsSection`.

## List pieces

- **`SettingsList.vue`**: the one settings list. Handles every state: error (Try again),
  loading skeleton rows, "Nothing matches" when a search or filter is on (Clear search), the
  empty state (icon, title, one line pointing at the page's primary action), then a bordered
  list with an optional column header and **Show more** when there are more pages. Rows come
  from the default slot (`{ item, index }`).
- **`SettingsListItem.vue`**: one row. Title (greyed when `muted`, e.g. disabled or inactive)
  and subtitle; `prefix` (avatar, provider icon), `badges` (`TaskyBadge`: Default, Inactive,
  Disabled), `meta` (owner, scope, priority) and `actions` (Enabled switch, ⋯ menu with an
  accessible name) slots. With `@open` the title area is a button that opens the record, and a
  chevron shows when there are no actions.
- **`SettingsSearch.vue`**: the search box above a list (debounced, with Clear search).
- **`DuplicateDialog.vue`**: "Duplicate …" for SLA policies, holiday schedules, assignment
  rules and saved replies: one name field and **Make a copy**.

Used by Agents, Teams (and a team's members), Departments, SLA Policies, Business Holidays,
Assignment Rules, Field Dependencies, Saved Replies, Email Accounts, Email Notifications,
Telephony providers and pending invites.

## Pages

| Page | Notes |
| --- | --- |
| Profile | Photo (upload, change and remove are buttons), availability, emails and signature (sub-page), password. |
| Preferences | Theme (a radio group of buttons; the current theme carries the brand border), language and timezone; saving reloads the app. |
| Email Accounts | List with each account's role badge (Default Inbox, Default Sending…; info tone when that direction is on). Add and edit are sub-pages with Back, Save in the header and Pull emails now. |
| Email Notifications | List of the four emails; each opens an editor with Enabled and Save in the header. |
| General | Branding, Tickets, Workflow and knowledge base, User sign-up sections. |
| Agents | Search, All/Active/Inactive filter, role menu per agent (managers), deactivate/reactivate. Invite agents is the primary action. |
| Invite Agents | Emails and role, Send invites; pending invites with Cancel invitation. |
| Teams | List; a team page with Add members, Enabled and a ⋯ menu (assignment rule, rename, access, delete). |
| Departments | Add department (labelled field), then the ordered list with move, rename, activate and delete inline. See [departments.md](departments.md). |
| SLA Policies, Business Holidays, Assignment Rules, Field Dependencies, Saved Replies | List page + editor sub-page with the shared header. |
| Sign-off templates | List (inactive greyed, question count) and an editor sub-page with Active, Back and Save in the header. See [project-signoff.md](project-signoff.md). |
| Content, Tasks, File storage, CRM | TBO pages; sections of `SettingRow`s, Save in the header, load errors with Try again. See [content-calendar.md](content-calendar.md), [ai-task-descriptions.md](ai-task-descriptions.md), [project-files.md](project-files.md), [tbo-crm-integration.md](tbo-crm-integration.md). Tasks also has the Support hours section (email the customer when their hours run low; [support-contracts.md](support-contracts.md)). CRM also has the Invoicing section, whose pickers are read live from the CRM site and checked on save ([timesheet-invoicing.md](timesheet-invoicing.md)). |
| Follow-ups | System Managers and Agent Managers. Enabled in the header; Delivery (digest times, Send me a test digest), Escalation ladder, Task rules and Ticket rules (a switch and threshold per rule), Customer follow-up, Working hours (read from the default SLA) and a Preview of each person's digest. See [follow-ups.md](follow-ups.md). |
| Chat & Teams | System Managers and Agent Managers. Every HD Chat Settings field; secrets masked, with Send me a test and Send a test to the channel. See [Chat & Teams](#chat--teams) below. |
| Telephony | Default medium, then Twilio and Exotel as list rows that open their sub-pages. |
| ERPNext | Enable switch, in-sync / sync-needed status (success or warning soft panel, with icon). |

## Chat & Teams

`desk/src/components/Settings/Chat/` (`ChatSettings.vue`, `SecretField.vue`, `SendTest.vue`),
backed by `helpdesk.api.chat_settings`, which checks for System Manager or Agent Manager
itself and saves HD Chat Settings with `ignore_permissions` (the doctype stays writable by
System Managers only). No new storage: it is the same Single the desk form edits.

- **Header**: Enabled switch and Save changes.
- **Delivery**: platform (Microsoft Teams or Slack) and *Email people who can't be reached
  in chat*.
- **Microsoft Teams** (Teams only): Direct Message Workflow URL and Escalation Channel
  Workflow URL. **Slack** (Slack only): Bot Token and Escalation Channel ID.
- **Error alerts**: post hub errors to the escalation channel, and the titles to ignore.
- **Last delivery problem**: shown only when the Error Log has a chat delivery failure
  (`error_alerts.CHAT_ERROR_TITLES`); its title and time, never the traceback, which can
  hold the URL.
- **Creating the Teams workflows** (Teams only): the two templates, *Who can trigger the
  flow* = Anyone, Recipient = `triggerBody()?['recipient']`, and the payload
  `chat_notifications.teams_message` posts (plus `recipient` for direct messages).

**Secrets** (the bot token and both workflow URLs; a workflow URL carries its `&sig=` key):
once saved they never go back to the browser. `get_settings` returns
`secrets[field] = {set, masked}`, the mask being the URL's scheme and host or the token's
`xoxb-` prefix. A saved secret shows masked with **Replace** (an input with Cancel) and, for
the two optional URLs, **Remove** (Undo until saved). `save_settings(values)` keeps a
secret whose key isn't sent (or is null), stores a sent value trimmed, and removes it for
"". The URLs are checked by `HDChatSettings.validate` (`teams_url_problem`); its message
starts with the field's label, so the page shows it under that field as well as in a toast.

**Send a test** (`send_test(target)`, POST, `direct` or `channel`): uses the saved settings,
so the buttons are disabled while the page has unsaved changes. It returns `{ok, message}`:
sent, not set up yet ("add it, save, then test again"), or the platform's error with a hint
(`chat_notifications.describe_error` / `error_hint`: Teams HTTP 401/403/404/405, Slack
`invalid_auth`, `not_in_channel`, `missing_scope`…). A network error shows only its kind,
since its text can hold the URL. The desk form's *Send test message*
(`chat_notifications.send_test_message`) uses the same wording. Tests:
`helpdesk/tests/test_chat_settings.py`.

Settings → Follow-ups links here from its Delivery section ("Where do messages go?").

## Copy

- Buttons say the outcome: Save changes, Create policy, Add department, Invite agents, Send
  invites, Make a copy, Test connection, Sync now.
- Errors say what happened and what to do ("Save your changes first", "Add a name and at
  least one member, then create the team.").

# Ticket owners: who gets a customer's new tickets

The owner's request (2026-10-14): every customer has a **ticket owner**. A new ticket from
that customer is assigned to the owner automatically, anyone can still reassign it, and the
owner hears about it on Microsoft Teams. Many tickets sat unassigned (Hydrotech, Adka General
Contracting); tickets with no customer (Grafana alerts, system mails) stay as they are.

## Fields

On **HD Customer** (doctype JSON, section "Ticket Owner"):

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket_owner` | Link → HD Agent | Gets the customer's new tickets |
| `backup_ticket_owner` | Link → HD Agent | Gets them while the owner is on leave or inactive |

HD Agent is named after its user, so the value is the user ID the ToDo uses (`assign_to`).

`HDCustomer.validate_ticket_owners`, only when either field changes:

- Only the people who may set owners change them (`can_set_ticket_owner`, below), otherwise
  PermissionError. This also stops a portal customer manager (who can write their customer)
  from picking an owner.
- Both must be **active agents**: an HD Agent with `is_active` and an enabled User
  (`active_agents`).
- The backup needs an owner and must be someone else.

A customer whose owner was later deactivated can still be saved for other edits; the rule
only checks the fields that changed (an empty value sent as `""` or `None` is no change).

## Who may set owners

`can_set_ticket_owner(user)` in `hd_customer.py`: System Managers, Agent Managers, Project
Managers (`tasky.permissions.is_project_manager`) and department heads (`can_manage_team`).
It is in the session payload as `can_set_ticket_owner` (`authStore.canSetTicketOwner`).
Everyone else sees the owners read-only.

## Who gets a new ticket

A ticket only ever goes to someone **working today** (the owner's rule of 29 Oct 2026,
Phase 12): an active agent, not a Sales Employee, not on approved leave and not set to an
**Unavailable** status (`ticket_assignment.working_today`). `ticket_assignment.pick` follows
this chain, and the first person working today takes it:

1. The **owner** (`HDCustomer.ticket_owner_today`).
2. The **backup**, while the owner is not working.
3. The **least busy on the customer's project team**: members of the customer's open projects
   whose project role is Developer or Support Engineer, the fewest open ticket assignments
   first (`ticket_assignment.from_project_team`).
4. The **team's assignment rule**, which for tickets only picks people working today, the
   Active ones before the Away ones, and of those the least busy (Weighted Distribution keeps
   its weights among them). It never falls back to someone on leave or Unavailable
   (`HelpdeskAssignmentRule.get_ticket_user`); other doctypes keep the old rule.
5. **Nobody**: the ticket waits. Every 10 minutes `ticket_assignment.ask_for_unassigned` brings
   a customer's open ticket that is still unassigned 5 minutes after it came in to the
   customer's **Project Coordinators** working today, else the admins (System Manager, Agent
   Manager), once per ticket: a Teams message (or email) and a line in the ticket's chat.

A Sales Employee counts as not working here (they can't be given tickets,
[departments.md](departments.md#sales-wall-sales-employee)).

Leave is the approved leave synced from tboindia into **HD Leave** at 06:15
(`work_calendar.on_leave`, the same reader the follow-ups use). A **half day still counts as
working**, as in the follow-ups.

### When someone goes on leave, and comes back

Every morning at 06:30, after the leave sync (and after **Sync holidays now**),
`ticket_assignment.daily` runs:

- **Give back** (`give_back`): a ticket moved away from someone goes back to them once they work
  again, **if nobody worked on it meanwhile** (no reply sent, no comment and no chat message
  by a person since the move). Otherwise it stays with whoever has it.
- **Move** (`hand_over_from_leave`): an open or paused ticket whose assignees are **all** on
  leave today goes to the next in the chain above (someone working who still has it keeps
  it). The ticket remembers whose it was (`custom_away_assignee`, `custom_moved_on`); the new
  assignee is told in Teams; the ticket's chat says "Moved to Vishnu Prasad: Rahul Nair is on
  leave until Fri 31 Oct." When nobody is free, the coordinators are asked.

The assignee picker on the ticket shows "On leave until …" and does not offer someone on
leave all day (a half day still can); they can still be taken off a ticket.

### Copilot's developer

Copilot's "the customer's developer" (hand-overs, approvals, the error watch, ticket news) is
whoever takes the customer's tickets today: `ticket_assignment.developer_of`. The older
Copilot field **Assigned Developer** on HD Customer is hidden; it only counts for a customer
with no owner, and the patch `copilot_developer_is_ticket_owner` made it the owner where a
customer had none.

### When it runs

`HDTicket.assign_customer_owner()`:

- **On insert** (`after_insert`), after the customer is resolved (`set_customer` runs in
  `before_validate`, from the contact). A new ticket that still has no customer, isn't an
  alert and wasn't raised by an agent may then get one from the sender's email domain
  (`set_customer_from_domain`, see [ticket-intake.md](ticket-intake.md#customer-detection)).
  Owner assignment itself covers every channel, since every channel inserts an HD Ticket:
  email, the customer portal, the agent's New ticket, the API, the hub-client pull
  from customer sites (`ticket_puller`) and the Chatwoot bridge (including its stand-in
  default customer, if that customer has an owner).
- **Customer set later** (`on_update`, `assign_owner_of_customer_set_later`): a ticket that
  came in without a customer gets the owner once, when its customer is first set, and only if
  it has no open assignment then. Later customer changes, updates and reopening never
  reassign.
- **No customer**: nothing happens.

### Precedence over the assignment rules: why after_insert

Frappe's Assignment Rules (the HD Team round robin and the base "Support Rotation") run as an
`on_update` doc event (`frappe.automation.doctype.assignment_rule.assignment_rule.apply`).
On insert Frappe calls `after_insert` **before** `on_update`, and `apply` only assigns when a
document has no open assignment; it only unassigns ToDos the rule itself made
(`apply_unassign` checks `ToDo.assignment_rule`). So assigning the owner in `after_insert`
means:

- the owner wins over the team rotation;
- there is never a second ToDo: the rule sees the owner's ToDo and does nothing;
- a team change later doesn't unassign the owner through the rule (the ToDo isn't the rule's).

This needed no flag and no change to Frappe or to the rule override. The alternative, a
`before_insert` flag that skips the rule, would have meant patching Frappe's `apply` for one
doctype.

If a rule's assignment is already there when the owner is applied (only possible when the
method is called on an existing ticket), its ToDos are withdrawn first, even one the rule
gave the owner, so the assignment, activity and notice are the owner's. A person's
assignment is never replaced.

**Team:** a ticket with a team (agent group) still goes to the owner even when the owner
isn't in that team. The owner knows the customer; the team stays on the ticket. The existing
`remove_assignment_if_not_in_team` only acts when someone changes the team later: it now
also returns during the insert (`flags.in_insert`), where it used to return only because
the in-memory `_assign` was still empty. `assign_customer_owner` keeps that copy in step with
the database, so without the guard it would have taken the owner off on insert.

**Routing after triage** ([ticket-intake.md](ticket-intake.md#routing)) sets the team later,
as the automation user. It saves with `flags.keep_assignment`, so
`remove_assignment_if_not_in_team` leaves the owner's ToDo alone, and the team's round
robin skips the ticket because it already has an open assignment: the owner keeps it.

### What is recorded

- The ToDo is assigned by the automation user (HDS Hub Settings, "TBO AI").
- A ticket activity, credited to the automation user, not to whoever's session created the
  ticket (a portal customer, an email job): "assigned Reshma Rao, ticket owner of Hydrotech",
  or "assigned Anu Varghese, backup ticket owner of Hydrotech (Reshma Rao is on leave until
  Fri 16 Oct)", "(… is inactive)" or "(… is set to Unavailable)", or "assigned Arjun Menon,
  the least busy on Hydrotech's project team (…)".
- The same, in a sentence, in the ticket's chat (`ticket_assignment.tell_chat_about`), so
  everyone who opens the ticket sees who has it and why.

## Notification

Asked by Rubashed (2026-10-22): the owner and the backup both hear about a customer's new
ticket, with a sound for new tickets, and about its resolution and status changes.

### A new ticket

`HDTicket.notify_ticket_owner` sends the person who takes the ticket (the owner, or the
backup while covering) one notice of type **New Ticket** through
`work_reminders.notify_users`: the helpdesk panel, plus a Teams direct message when HD Chat
Settings is on (email when chat is off or can't reach the person, as for every reminder),
plus a mobile push when Mobile push is on:

> New ticket #29 from Hydrotech assigned to you: Material Request – Central Warehouse store
> not showing
> Priority: High · First response due 14 Oct, 13:12
> You're the backup owner while Reshma Rao is away. (backup only)

`HDTicket.notify_backup_owner` gives the **backup** a quiet copy while the owner takes it:
panel and realtime only, no Teams message, email or push (`deliver=False`), so a backup isn't
pinged for every ticket of a customer they only cover:

> New ticket #29 from Hydrotech for Reshma Rao (you're the backup): Material Request – …

**The owner on leave or inactive hears nothing** about new tickets: the backup takes them
and the owner isn't working. They still see the ticket in the customer's list when back.

**Never about your own ticket:** nobody gets a new-ticket notice for a ticket they raised
(`raisers()`: the ticket's `owner` or `raised_by`), e.g. an owner logging a call for their own
customer. Nobody is notified when the rules decide instead of the owner, or when a person
assigned the ticket while creating it.

The links open `/helpdesk/tickets/<id>`.

**Not sent twice:** a plain assignment sends no Teams message. HD Notifications of type
Assignment stay in the panel only (`HDNotification.deliver` only delivers Mention, Reminder
and New Ticket), so this is the only chat message. The assignment itself still makes Frappe's
own "assigned to you" Notification Log, as every assignment does; whether that also emails is
the person's Notification Settings (Assignments), unchanged by this feature.

### The new-ticket sound

A per-person preference, **off by default**: the User custom field `hd_new_ticket_sound`
(`setup/install.py`, label "Sound for New Tickets"), set in **Settings → Preferences →
Notifications → Sound for new tickets** (a switch, and **Play** to hear the tone). It is in
the session payload as `new_ticket_sound` (`authStore.newTicketSound`); saving it reloads the
session, not the page.

`HDNotification.announce` publishes `helpdesk:new-notification` with `sound: true` only for
a New Ticket notice that is delivered, i.e. the person taking the ticket, not the backup's
quiet copy. The notification store (`stores/notification.ts`, `announceNewTicket`) then:

- always shows a toast with the notice (first line as title, the rest below) and **Open**;
- plays `NEW_TICKET_TONE` (`composables/notificationSound.ts`: a lower three-note figure, so
  it is told apart from the completed-task chime) only when `sound` is set, the person turned
  the preference on, **and** `canPlaySound()`: the browser reports the page has had a click
  or key press (`navigator.userActivation.hasBeenActive`). Browsers block audio before that;
  where the browser can't say, it tries and fails quietly. Without sound the toast and the
  bell's count still show.

The tab has to be open: there is no sound from a closed tab (the Teams message and mobile
push cover that).

### Status changes and customer replies

`HDTicket.notify_ticket_update` (`on_update`) sends one **Ticket Update** notice per change
to each follower, panel and realtime only (no Teams, email or push: these come often, and
the follow-ups chase what is late):

| Change | Notice |
| --- | --- |
| Status moves to a Resolved-category status (Resolved, Closed) | "Celine Joseph marked #29 Resolved: …" |
| Status category goes back to Open from Paused or Resolved | "Celine Joseph reopened #29: …" |
| A customer's message arrives (email or portal), whether or not it reopens | "Hydrotech replied on #29: …" |

A change by no person (the auto-close job, an email job) reads "#29 was marked Closed: …".
Other status changes (Open → Replied, Paused) send nothing.

**Followers** (`ticket_followers`): the assignees, the customer's ticket owner (always), and
the backup **only while covering** (`ticket_owner_today()` returns the backup, i.e. the owner
is on leave or inactive). The person who made the change is left out, and so is a Sales
Employee (`new_notification`). The owner always follows because the customer is theirs even
when someone else works the ticket; the backup only while covering, so they aren't told about
every ticket of a customer they normally don't look after.

**One notice per change:** this replaced the old reopen notice (type Reaction, assignees
only), so an owner who is also the assignee gets one notice, not two. A reply that reopens
the ticket is told once, as the reply. `mark_customer_reply` (called from
`on_communication_update` for a Received Communication) keys the notice by the
Communication (`dedupe_key` `ticket-reply:<communication>`): the message that opened the
ticket isn't a reply (no earlier Received Communication), and an incoming email, which
Frappe saves twice, is told once. A portal reply first saves the reopened status
(`create_communication_via_contact`, flagged `skip_update_notice`) and then creates its
Communication, which sends the one notice. Every message from a chat bridge counts as a
reply.

The 4-working-hour **Customer replied, no answer** follow-up ([follow-ups.md](follow-ups.md))
is separate: it chases a reply nobody answered.

### In the panel

`Notifications.vue` and `MobileNotifications.vue` show New Ticket and Ticket Update notices as
their message (`isTextOnly()` in `stores/notification.ts`), with a neutral circle and a Lucide
icon (`components/notifications/NotificationIcon.vue`: ticket-plus for a new ticket, ticket for
an update; the reminder keeps its alarm clock on `warning`). They open the ticket.

## Screens

- **Customer page** (`/customers/:id`): the header names the ticket owner and backup
  (`components/customer/TicketOwnerInfo.vue`), with "(On leave until …)" or "(inactive)"
  when they can't take new tickets. People who may set owners get **Change** / **Set owner**,
  which opens `components/customer/TicketOwnerDialog.vue` (owner and backup pickers of active
  agents, each showing their leave).
- **Customers list** (`/customers`): a **Ticket owner** column ("No owner" in gray), the
  owner on the second line on phones, and an owner filter (Any owner / No owner, in the URL
  as `owner`) so managers can fill the gaps. With "No owner" and nothing left: "Every customer
  has a ticket owner".
- **Bulk "Set ticket owner"**: people who may set owners get checkboxes (`md` and up, like
  bulk delete); the selection bar's **Set ticket owner** opens the same dialog for all of
  them (one selected customer too). The backup picker defaults to "Keep each customer's
  backup". `DirectoryList` gained a
  `selectable` prop and a `selection-actions` slot for this; bulk delete is unchanged.
- **Ticket page**: the Details panel shows **Customer owner** under the customer (read again
  when the customer changes; "Couldn't load" with Retry when the lookup fails, "Not set" only
  when it succeeded and there is none).
- **Settings → CRM → Customers**: **Fill ticket owners from CRM account managers** (below).

Shared: `composables/assignablePeople.ts` loads `helpdesk.tasky.api.get_users` once for the
pickers and names.

## APIs

| Method | Who | What |
| --- | --- | --- |
| `helpdesk.api.ticket_owner.set_ticket_owner` POST (no agent-only guard: `can_set_ticket_owner` decides) (`customers`, `ticket_owner`, `backup_ticket_owner?`) | `can_set_ticket_owner` | Sets the owner of one or many customers, all or none. An empty owner clears both. Without `backup_ticket_owner` each customer keeps its backup, except a backup that is the new owner (cleared). `""` clears the backup. |
| `helpdesk.api.directory.get_customer_directory` | agents | Rows carry `ticket_owner` and `ticket_owner_name`; `owner=none` lists customers without an owner |
| `helpdesk.api.crm.fill_ticket_owners_now` POST | System and Agent Managers | The CRM fill below |
| `helpdesk.api.mobile.get_ticket` | agents | `customer_owner` `{user, full_name}` or null ([tbo-smart-api.md](tbo-smart-api.md)) |

## Filling owners from the CRM

TBO's customers come from tboindia (see [tbo-crm-integration.md](tbo-crm-integration.md)).
A **CRM Organization** has no account owner field. An ERPNext **Customer** on that site has
`account_manager` (a user), so that is what is used.

**Fill ticket owners from CRM account managers** (`integrations.crm.customers.fill_ticket_owners`)
is a one-time action, run when someone clicks it:

- Only customers **without** a ticket owner are filled; owners already set are never changed.
- Matched by customer name like the customer sync (ignoring case and extra spaces), and the
  account manager by email (ignoring case) to an **active agent** here.
- Two ERPNext Customers with the same name and different account managers: neither is
  picked; the customer is listed as ambiguous and stays empty.
- The owner is written only while it is still empty (a conditional update), so an owner
  someone set meanwhile stays.
- The result says how many were filled, which customers have an account manager who isn't
  an active agent here, and which were ambiguous.
- No ERPNext on the CRM site (or no access): the error is shown and nothing changes.

## After deploy

1. `bench migrate` adds the two fields, the User field `hd_new_ticket_sound` and the New
   Ticket and Ticket Update notification types.
2. Set owners: Customers → filter **No owner** → select → **Set ticket owner**, or each
   customer's page. Or try **Settings → CRM → Fill ticket owners from CRM account managers**
   first.
3. For Teams messages, Settings → Chat & Teams (HD Chat Settings) must be on with direct
   messages working (see [follow-ups.md](follow-ups.md#after-deploy)); otherwise owners get
   the email fallback.
4. Each person who wants the new-ticket sound turns it on in Settings → Preferences →
   Notifications (off by default).
5. Existing unassigned tickets are not changed. A ticket that is still unassigned gets its
   owner only when its customer is first set.

## Files

- `helpdesk/helpdesk/doctype/hd_customer/hd_customer.json`, `hd_customer.py`
  (`validate_ticket_owners`, `ticket_owner_today`, `can_set_ticket_owner`, `active_agents`)
- `helpdesk/helpdesk/doctype/hd_ticket/hd_ticket.py` (`assign_customer_owner`,
  `assign_owner_of_customer_set_later`, `log_owner_assignment`, `notify_ticket_owner`,
  `notify_backup_owner`, `notify_ticket_update`, `ticket_followers`, `mark_customer_reply`)
- `helpdesk/helpdesk/doctype/hd_notification/` (New Ticket and Ticket Update types,
  `announce` sound flag, `deliver`), `helpdesk/mobile_push.py` (`PUSH_TYPES`)
- `helpdesk/api/ticket_owner.py`, `helpdesk/api/directory.py`, `helpdesk/api/auth.py`,
  `helpdesk/api/mobile.py`, `helpdesk/api/crm.py`, `helpdesk/integrations/crm/client.py`,
  `helpdesk/integrations/crm/customers.py`
- `desk/src/components/customer/TicketOwnerDialog.vue`, `TicketOwnerInfo.vue`,
  `desk/src/composables/assignablePeople.ts`, `desk/src/components/DirectoryList.vue`,
  `desk/src/composables/directory.ts`, `desk/src/pages/customer/Customers.vue`,
  `Customer.vue`, `desk/src/components/ticket-agent/TicketDetailsTab.vue`,
  `desk/src/components/Settings/CRM/CRMSettings.vue`
- `desk/src/stores/notification.ts`, `desk/src/composables/notificationSound.ts`,
  `desk/src/components/notifications/Notifications.vue`, `NotificationIcon.vue`,
  `desk/src/pages/MobileNotifications.vue`,
  `desk/src/components/Settings/Preferences/Preferences.vue`, `desk/src/stores/auth.ts`
- `helpdesk/ticket_assignment.py` (the chain, leave moves, coordinators asked, Copilot's
  developer), `helpdesk/overrides/assignment_rule.py` (`get_ticket_user`), the patch
  `helpdesk/patches/v16_0_2/copilot_developer_is_ticket_owner.py`,
  `desk/src/components/ticket-agent/AssignTo.vue` and `desk/src/composables/onLeave.ts`
  (`awayAllDay`)
- Tests: `helpdesk/tests/test_ticket_assignment.py`, `helpdesk/tests/test_ticket_owners.py`, `helpdesk/tests/test_ticket_alerts.py`
  (helpers `make_owned_customer`, `get_open_assignees`, `get_ticket_owner_activity`,
  `get_ticket_notices`, `FakeCRM.account_managers` in `test_utils.py`)

# Ticket intake: which mail becomes a ticket, and where it goes

The owner's request (2026-10-14), after a read-only audit of the hub's tickets from
29 Sep to 14 Oct. Of 26 tickets, 13 were noise:

- 10 from Grafana: 6 alert mails (`[FIRING:1]`, `[RESOLVED]`, `[FIRING:1, RESOLVED:1]`),
  each opening its own ticket that stayed Open, and 4 Grafana Cloud account mails;
- 2 "Weekly energy points summary" mails and 1 Anthropic mail.

10 of the 12 SLA failures were that noise. 23 of 26 tickets were unassigned, every ticket
was type Bug and priority Medium (the defaults), the triage's priority and category were
stored but never used, 0 of 74 contacts were linked to a customer and only 1 of 26
customers had a domain. Client-site imports for one customer failed, and only 2 tickets
ever reached Resolved, so the feedback mail went out twice and there were no ratings.

The owner said "no questions, do the recommended way"; the decisions below are recorded
with their reasons.

Everything is set in **Settings → Ticket intake** (`HD Intake Settings`, a Single), for
System Managers and Agent Managers.

## Mail rules

`helpdesk/intake.py`. Rules are an ordered table (`HD Intake Rule`): Name, On, Sender
(addresses or domains, separated by commas or new lines; a domain also matches its
subdomains, the same matching as the built-in filter, `email_filter.sender_matches`),
Subject (a regular expression, not case-sensitive) and an action. A rule needs a sender, a
subject or both, and every pattern it has must match. **The first enabled match decides.**

| Action | What happens |
| --- | --- |
| **Ignore** | No ticket. The mail is logged in **HD Intake Log** ("Ignored"). |
| **Alert** | A ticket of type **Alert**, or, when that alert is already open, a comment on it (below). |
| **Merge into open alert** | Only ever a comment on an open alert with the same key; with none open it is logged as Ignored. Never opens a ticket. |

The built-in filter (HD Settings: *Ignore automated senders*, `noreply@`, `notifications@`,
`mailer-daemon@`…, and *Always ignore mail from*) runs **after** the rules, so a rule can
still turn a monitor that mails from a noreply address into alerts. It is shown and edited on
the same page; its fields stay in HD Settings. Replies to a ticket are never filtered.

### Where it runs

- **Incoming mail** (`overrides/email_account.CustomInboundMail.process`): a new mail (not
  a reply, not already received) goes through `intake.handle_new_mail` first. An ignored mail
  or a repeat of an open alert is handled there and `process()` returns nothing, so no
  Communication or ticket is made and nothing is rolled back (the log and comments are kept).
  A mail Frappe would thread onto an old ticket by its subject still is, except a monitor's:
  alerts group by their own key, never onto an old closed alert ticket.
- **Any ticket opened by email** (`HDTicket.apply_intake_rules`, `before_insert`, only when
  `email_account` is set, as before): Ignore raises `UnwantedTicketEmail` (Frappe's receiver
  rolls back quietly, as the old filter did); Alert sets the type and `alert_key`.

### Monitoring alerts

`intake.parse_alert(subject)`. Grafana's subject is `[STATE] name group-labels
(common-labels)`:

- **Key** (`HD Ticket.alert_key`, indexed): the alert name and group labels, lower-cased,
  e.g. `site down tbocloud`.
- **Labels**: the words in parentheses. Grafana's common labels change as single alerts in a
  group fire and resolve: on the hub the FIRING mail said `(TBO Team critical tboindia
  production)` and its RESOLVED mail `(TBO Team critical production)`. So the labels only
  rank candidates (most labels in common, then newest); the key decides.
- **State**: resolved only when every part is resolved (`RESOLVED`, `OK`, `RECOVERED`, `UP`).
  `[FIRING:1, RESOLVED:1]` still has something firing.

A new alert opens a ticket of type Alert. A repeat while it is open (Open or Paused) adds a
comment "Monitor update: …" with the first 1,500 characters of the mail, logged as
"Grouped". The monitor's resolved mail adds the comment and sets the status **Resolved by
monitor** (a Resolved-category status), logged as "Resolved". A resolved mail with nothing
open opens nothing.

Alert tickets:

- **No SLA**: `HDTicket.set_sla` clears `sla`, `agreement_status`, `response_by` and
  `resolution_by` for type Alert (`apply_sla` and the working-hours check skip a ticket
  without an SLA). Chosen over an SLA condition: a condition on the default SLA would still
  give alerts an SLA record and figures, and the hub has only the default SLA.
- **Not counted**: left out of Home's open, new-today, unassigned and SLA counts
  (`api/home.NOT_AN_ALERT`, which the app's `get_sla_summary` reuses) and of the follow-up
  ticket rules (`follow_ups.TicketRules`). SLA figures (Team insights' breaches) read
  `agreement_status`, which an alert never has. The Scoreboard counts tasks, not tickets.
- **No triage, no acknowledgement mail, no feedback request, no customer by domain.**
- **Teams channel** (optional, *Post monitor alerts to the escalation channel*): "Alert
  opened: …" when the ticket opens and "Alert resolved: …" when the monitor resolves it, to
  the escalation channel of Chat & Teams (`chat_notifications.post_to_channel`, the channel
  the error alerts use). Queued after the commit; a failure is only written to the log,
  since the error digest posts to the same channel.

### Defaults (seeded once, all editable)

`intake.ensure_intake_defaults`, run on install and by patch
`v16_0_2.ticket_intake_defaults`. It also creates the **Alert** ticket type and the
**Resolved by monitor** status. Rules are seeded only while the rule list and the public
domains are both empty, so an owner's edits are never overwritten.

| Rule | Sender | Subject | Action |
| --- | --- | --- | --- |
| Grafana alerts | `grafana.net` | `^\[(FIRING\|RESOLVED)` | Alert |
| Other monitoring alerts | | `^\[(FIRING\|RESOLVED)` | Alert |
| Grafana account mail | `grafana.com` | | Ignore |
| Grafana Cloud notices | | `verify your grafana\|grafana stack is active` | Ignore |
| Weekly energy points summary | | `^weekly energy points summary` | Ignore |
| Vendor newsletters | anthropic.com, canva.com, figma.com, notion.so, linkedin.com, facebookmail.com, medium.com, substack.com, quora.com, zoom.us | | Ignore |

The vendor list holds only vendors' own domains, never mail services customers send from
(SendGrid, Mailchimp…), which would drop real tickets.

### Recently kept out

The page lists the last 20 HD Intake Log rows. Log Settings clears rows older than 30 days
(`default_log_clearing_doctypes`).

### Apply rules to open tickets (one-off cleanup)

The rules only see new mail. **Apply rules to open tickets** applies them to the open
tickets (Open or Paused, not merged) that came in by email, in the order they arrived,
up to 500. **Preview changes** (`helpdesk.api.intake.preview_cleanup`) lists what would
change and changes nothing; only then does **Apply N changes**
(`apply_rules_to_open_tickets`, POST) run the same plan as the automation user. It never
runs on its own. Steps:

| Step | For | What it does |
| --- | --- | --- |
| Close | An ignored sender, or a resolved alert with nothing open | Comment "Closed by the intake rule …", status Closed |
| Mark as alert | The first ticket of an alert | Type Alert and its key; the SLA is cleared |
| Group into #N | A later ticket of the same alert | Comment on #N, closed as merged into it (`is_merged`, `merged_with`) |
| Resolve | The alert, when a later ticket is its RESOLVED mail | Status Resolved by monitor |

Grouping doesn't use the ticket merge action (`hd_ticket/api.merge_ticket`), which emails
the sender (here Grafana) about the merge. No feedback mail goes out for a cleaned-up ticket
(`flags.skip_feedback`). A step that fails is reported and the others still run.

## Routing

`helpdesk/routing.py`, called by `triage.run_triage` after a triage succeeds
(`_route`; a failure is logged and rolled back, the triage stands). With **Apply AI
triage** on:

- **Priority**: the triage's priority (Critical becomes Urgent, the hub has no Critical),
  while the ticket still has a default priority (empty, Medium, HD Settings' default, its
  type's or its SLA's default) and no person has changed it.
- **Ticket type**: the category's route type, else from the request type (question →
  Question, issue → Bug), while the ticket still has the default type (empty, Unspecified
  or HD Settings' default, Bug on the hub) and no person has changed it. A customization is
  typed by `customization.record_triage_estimate`, which runs first and now also treats the
  default type as unset.
- **Team**: the category's route team (HD Intake Route: triage category → team and ticket
  type), else the **Default team**, while the ticket has no team and no person cleared it.

"A person changed it" means an HD Ticket Activity line `set priority to …` / `set type to …`
/ `set team to …` (or `cleared …`) by anyone but the automation user. The routing saves once,
as the automation user (`automation.as_automation_user`), so its own activity lines are
TBO AI's.

### Assignment

1. The customer's **ticket owner** gets the ticket on insert
   ([ticket-owners.md](ticket-owners.md)), before triage.
2. Routing sets the team; the team's Assignment Rule (round robin) then assigns a ticket
   nobody has. It skips one with an open assignment, so the owner keeps it.
3. Routing never takes an assignment away: it saves with `flags.keep_assignment`, which
   makes `remove_assignment_if_not_in_team` leave a person's or the owner's assignment alone
   even when they aren't in the new team.

A team's rule only assigns when the team has members (HD Team syncs them into the rule) and
the rule is on. On the hub *Billing* and *Product Experts* have no members, so the page warns
for every team it routes to: "Team X has no members, tickets routed there stay unassigned"
or "Team X's round robin is off …", with **Open Teams**. The data is
`api/intake.teams()` (members per team, and whether its rule is on).

## Customer detection

On a **new** ticket that has no customer after `set_customer` (the contact's), with **Match
customers by email domain** on, not an alert and not raised by an agent:

- `hd_customer.customer_for_email`: the sender's domain against each customer's **Domain**
  and **Other Email Domains** (new Small Text field on HD Customer, one per line; on the
  customer's Edit dialog). A subdomain matches (`mail.acme.com` → `acme.com`). Domains are
  normalised (`https://www.Acme.com/about` → `acme.com`).
- **Public mail domains** (Settings, one per line; seeded with gmail.com, outlook.com,
  hotmail.com, yahoo.com, icloud.com, live.com and others) never match.
- A domain two customers share matches neither.
- The domain → customers map is cached (`hd_customer.domain_customers`, 10 minutes) and
  cleared whenever an HD Customer is saved, renamed or deleted, and after the CRM fill, so
  a new ticket doesn't read every customer.
- The sender then becomes a contact of that customer (`hd_customer.add_customer_contact`,
  moved from the content portal's `add_portal_contact`; it adds the member row without
  saving the customer, so no portal role is granted). Their next ticket finds the customer
  through the contact, the usual way. Only a domain match links a contact: an agent raising
  a ticket for a customer is never added as its contact.

It runs before `after_insert`, so the customer's ticket owner gets the ticket.

**Fill customer domains from the CRM** (`integrations/crm/customers.fill_customer_domains`,
`helpdesk.api.crm.fill_customer_domains_now`, POST, System and Agent Managers): customers
without a Domain take their CRM Organization's or ERPNext Customer's website, matched by
name like the customer sync. Preview first, then Fill. Left empty: two CRM records with
different websites, a public mail domain, a domain another customer already has. A Domain
typed in meanwhile is kept (conditional update).

## Client-site tickets (ticket puller)

`ticket_puller._create_hd_ticket`. Imports for one customer failed nine times with "The
selected customer … is not linked to the contact None": the pull that follows a site's ping
(`support_hub.ticket_raised`, allow_guest) runs as **Guest**, and `HDTicket.set_customer`
refuses a customer the contact doesn't belong to unless an agent raises the ticket. The
sender wasn't a contact at all. Now:

- The sender is the Support Ticket's **Raised By**, else its **owner** (the customer site
  user who created it), else the customer's own **Email ID**. A user ID such as
  `Administrator` is no address; before, an empty one became the hub's session user, which is
  why two tickets had `raised_by = Administrator`.
- The sender becomes a contact of the connection's customer (`add_customer_contact`).
- The ticket is inserted as the automation user, so the import never depends on who the job
  runs as.

The two existing tickets raised by Administrator are not changed.

## Customer feedback (CSAT)

Recommended option, implemented: **Ask for feedback on close** (on by default). The feedback
mail (Email Notifications → Share feedback) used to go out only on HD Settings' *feedback
status* (Resolved on the hub), and agents close tickets straight from Open, so it almost
never went out. Now `HDTicket.should_request_feedback` also sends it when a ticket is
**Closed** without ever having reached that status (no `set status to Resolved` activity).
Rules, for both paths:

- **Once per ticket**: `HD Ticket.feedback_requested_on` is set when it is sent; reopening
  and closing again sends nothing.
- **Only to customers**: never for an alert, an agent's own ticket, an automated sender
  (`is_unwanted_sender`), a chat contact without email, a portal ticket (the portal asks for
  the rating itself) or an already rated ticket. A cleaned-up ticket sends nothing.

The alternative, making Resolved the default close path in the UI, was not chosen: it
changes how every agent works and still misses tickets closed by the auto-close job or the
client sites.

## Files

- `helpdesk/intake.py`, `helpdesk/routing.py`, `helpdesk/api/intake.py`
- Doctypes: `hd_intake_settings`, `hd_intake_rule`, `hd_intake_route`, `hd_intake_log`;
  fields `HD Ticket.alert_key`, `HD Ticket.feedback_requested_on`,
  `HD Customer.email_domains`
- `helpdesk/helpdesk/doctype/hd_ticket/hd_ticket.py` (`apply_intake_rules`, `is_alert`,
  `announce_alert`, `set_sla`/`clear_sla`, `set_customer_from_domain`,
  `link_sender_to_customer`, `should_request_feedback`, `is_customer_sender`,
  `reached_status`, `remove_assignment_if_not_in_team`)
- `helpdesk/helpdesk/doctype/hd_customer/hd_customer.py` (`add_customer_contact`,
  `normalize_domain`, `customer_domains`, `public_email_domains`, `customer_for_email`)
- `helpdesk/overrides/email_account.py`, `helpdesk/email_filter.py` (`sender_matches`),
  `helpdesk/triage.py` (`_route`, alerts skipped), `helpdesk/consts.py`
  (`ALERT_TICKET_TYPE`, `MONITOR_RESOLVED_STATUS`, `TRIAGE_CATEGORIES`),
  `helpdesk/automation.py` (`as_automation_user`), `helpdesk/ticket_puller.py`,
  `helpdesk/integrations/crm/customers.py`, `helpdesk/api/crm.py`, `helpdesk/api/home.py`,
  `helpdesk/follow_ups.py`, `helpdesk/api/customization.py`
- Patch `helpdesk/patches/v16_0_2/ticket_intake_defaults.py`
- `desk/src/components/Settings/Intake/IntakeSettings.vue`,
  `desk/src/components/Settings/SettingsPreviewAction.vue`, `settingsModal.ts`,
  `desk/src/composables/customer.ts`, `desk/src/components/customer/EditCustomerDialog.vue`
- Tests: `helpdesk/tests/test_ticket_intake.py` (helpers `set_intake_settings`,
  `make_mail_ticket`, `make_intake_mail`, `get_intake_logs`, `get_ticket_comments`,
  `make_domain_customer`, `make_ticket_type`, `log_activity_as` in `test_utils.py`)

## After deploy

1. `bench migrate`: the doctypes, the fields, the Alert type, the Resolved by monitor status
   and the default rules.
2. **Review the seeded rules** in Settings → Ticket intake.
3. **Apply rules to open tickets**: Preview changes, check the list, then Apply.
4. **Add team members** (Settings → Teams) for every team the routing uses, and pick a
   default team and the category teams; the page warns about teams without members.
5. **Set customer domains**: Preview domains / Fill from the CRM, then add the rest on each
   customer (Edit → Domain, Other email domains).

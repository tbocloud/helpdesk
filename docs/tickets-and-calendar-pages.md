# Tickets list and Calendar

Phase 2B of the UI work in [ui-guidelines.md](ui-guidelines.md): the agent tickets list and the
work calendar. Both keep every route, URL parameter, permission and feature they had; the
changes are the summary strip, row readability, states and the phone layouts. Shared blocks
(`StatTile`, `TaskyState`, `TaskyBadge`) are described in [workspace-pages.md](workspace-pages.md).

## Tickets (`/tickets`, agents)

`desk/src/pages/ticket/Tickets.vue` on top of the shared `components/ListViewBuilder.vue`.
**The customer portal (`/my-tickets`) renders the same `Tickets.vue`**, so every agent-only
change is behind `isCustomerPortal`: the portal has no summary strip, and its status, SLA cells,
phone rows and empty state are its own (see [customer-portal-and-kb.md](customer-portal-and-kb.md)).

- **Summary strip** (`components/ticket-agent/TicketSummaryStrip.vue`): five compact
  `StatTile` toggles: Open, Unassigned, First reply overdue, SLA breached, Waiting on customer.
  Each count is `frappe.client.get_count` on HD Ticket with the same conditions the tile
  applies, so the number and the list agree, and the count only includes tickets the agent may
  read (it goes through `get_list`). A tile sets `?filters=` on `/tickets` (dropping `view`,
  since the counts are across all tickets); pressing the active tile removes it. The pressed
  state is read back from the URL (`matchTicketFilter`), ignoring the "now" inside the deadline
  filters. Counts reload with the list on a new ticket (`helpdesk:new-ticket`); each tile keeps
  only its latest request's answer, so a slow older reply can't overwrite a newer count. A count
  that fails shows "—" and "Couldn't count. Select to retry."; selecting that tile counts again
  instead of filtering.
- **Filters in one place**: `pages/ticket/ticketFilters.ts` holds the conditions (`open`,
  `newToday`, `unassigned`, `slaBreached`, `firstReplyOverdue`, `waitingOnCustomer`, `rated`) and
  `ticketsLink()`. Home's `ticketLinks` (in `pages/home/homeMeta.ts`) are built from it.
- **`?filters=` support in `ListViewBuilder`** (all lists): the list now re-reads `?filters=`
  when it changes while the page stays open (a view switch is still handled by the view
  watcher), and it also applies `?filters=` when the user has no saved default view. Before,
  that case reset the list and dropped the filters, so Home's ticket links only worked for
  people with a default view. **Without `view` in the URL, `?filters=` replaces the filters**
  (the personal default view still supplies columns and sort), so a link's conditions are
  exactly what the list shows and a summary tile's count matches its list. With a `view`, the
  URL conditions are merged into the view's filters, overriding the same fields, as before.
- **Default columns** (`HDTicket.default_list_data`, agents without a saved default view): ID,
  Subject, Customer, Status, Priority, First response, Resolution, Assigned to, then Type, Team,
  Contact, Rating, Created. Saved views keep their own columns.
- **Cells** (agents): Priority is a `TaskyBadge` with the signal icon (Urgent red, High amber,
  others neutral). First response and Resolution are `TaskyBadge`s: Failed (red, alert icon),
  Fulfilled (neutral, check), Paused (neutral, pause), or, while the clock runs, **when the
  deadline falls** with a clock: "10:30 AM" today, "Tomorrow 10:30 AM", "Tue 2:30 PM" within six
  days, "13 Oct, 2:30 PM" later (`deadlineLabel`). It turns amber with at most **one working
  hour** left (`SLA_RISK_WORKING_SECONDS`) and is neutral otherwise. Hovering (and a screen
  reader) gives the exact deadline and the working time left: "Due Fri, Oct 9, 2026 10:30 AM ·
  30 working min left". A ticket without that deadline shows nothing, even when it is resolved
  or paused (no SLA means nothing to fulfil or fail). The SLA state logic (`responseSla`,
  `resolutionSla`), the deadline wording (`deadlineLabel`, `workingTimeLeft`, `slaHint`) and the
  agent badges (`slaBadge`, `priorityBadge`) live in `pages/ticket/ticketMeta.ts`, which the
  agent ticket page ([ticket-agent-page.md](ticket-agent-page.md)) uses too. The portal reads
  the same deadlines through `customerStatus.ts` instead ("Overdue", never "Failed").
- **Why a time, not "in 3h"**: `response_by` and `resolution_by` are computed in working time
  (the SLA's working days and hours, its holiday list with the 2nd/4th Saturdays off, plus hold
  time). A calendar countdown overstated what was left: "in 2h 14m" at 08:17 for a 10:30
  deadline when the desk opens at 10:00 (30 working minutes), or "in 4 days 6h" for a 24
  working-hour SLA over a weekend. The badge says when the deadline is, and the amber warning
  and tooltip count working time.
- **Working time left**: `composables/useSlaTimeLeft.ts` asks
  `helpdesk.api.ticket.get_sla_time_left(tickets)` for the visible rows that have a deadline, in
  one request per page (again when the rows or their deadlines change), and refreshes every 60
  seconds together with the "now" the labels and Failed states use. The server counts each
  ticket on its own SLA's calendar (see [ticket-agent-page.md](ticket-agent-page.md#api)). Until
  the count arrives, or if it fails (no toast; the old count is dropped and it retries on the
  next minute; only the latest request may set the counts), the badges show
  the deadline in neutral. Deadlines are read in the site's time zone (`dayjsLocal`, as the task
  timers do since #76) and shown in the agent's time zone, which defaults to the site's.
- **Escalation**: a ticket whose SLA warnings or breach have taken it up the follow-up ladder
  shows `EscalationBadge` ("Escalated to lead / head / managers") after its subject (agents
  only; `custom_escalation_level` is one of the list's rows). The SLA reminders themselves are in
  [follow-ups.md](follow-ups.md).
- **Summary strip and tones agree**: "SLA breached" and "First reply overdue" count tickets
  whose deadline has passed, which is exactly when a cell shows Failed; neither uses an "at
  risk" window, so the working-time warning changes no count.
- **Phones** (below 640px): `ListViewBuilder` renders a page's `#mobile-row` slot as a stacked
  list instead of the table. Tickets' row: subject (bold when unseen) with the resolution SLA
  badge, then `#id`, customer, status, priority and assignees. Row selection and bulk actions
  stay on wider screens.
- **Empty states**: first use ("Tickets from email and the customer portal show up here as they
  arrive."), filtered to zero (with a **Clear filters** button through `ListViewBuilder`'s
  `#empty-actions` slot), and the view-specific message. Clear filters removes `?filters=` (back
  to the view's own filters) or, when the filters were set on the page, empties them.
  `EmptyState` takes a default slot for such actions.
- The primary action reads **New ticket** for agents and customers.

## Calendar (`/calendar`)

`desk/src/pages/work/WorkCalendar.vue`; API `helpdesk.api.calendar.get_calendar(start, end,
team)` (unchanged): Teams meetings the user scheduled or is invited to, and their open tasks due
in the range; project leads and managers can switch to Mine / Team.

- **Header**: the frappe-ui `Calendar`'s `#header` slot renders the month as a heading that is
  also a date picker (jump to any month or day, through the calendar's `onMonthYearChange`),
  previous / Today / next (with accessible names) and a Day / Week / Month switch. Week is the
  default.
- **Event colours**: frappe-ui's calendar only resolves its own named colours, so the page adds
  `tbo-meeting`, `tbo-task` and `tbo-overdue` to the exported `CalendarColorMap`. Meetings and
  tasks are neutral (meetings a little darker); only overdue tasks are red; the selected event
  uses the brand soft colour. Each kind has an icon (`eventIcons`): video for meetings, a dot for
  tasks, a flag for key tasks and milestones, an alert for overdue, and the legend shows the
  same icons. Today's date is brand instead of black.
- **States**: an empty range says so next to the legend; a failed load shows the error with
  **Retry**; the refresh button spins while loading.
- **Phones**: an agenda for one week instead of the grid: previous / Today / next week, days
  with events only (today marked), meetings by start time then the day's tasks, each row opening
  its ticket or project, with **Join** for meetings that have a link. A meeting that spans
  several days is listed on each of them inside the week. Rotating into the phone layout starts
  on this week. Skeleton rows (hidden from screen readers, which hear "Loading calendar")
  while the first load runs; an empty week shows "Nothing this week".
- There is no "New meeting" here: a meeting is always scheduled from a ticket or task (the
  meeting needs its reference), through `components/meetings/ScheduleMeetingDialog.vue`.

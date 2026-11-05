# Agent ticket page

The page agents use most: `/tickets/:ticketId` (route `TicketAgent`). Goal: understand the ticket
at a glance and act fast. It follows [ui-guidelines.md](ui-guidelines.md); shared blocks
(`TaskyBadge`, `TaskyState`, `tone.ts`) are described in [workspace-pages.md](workspace-pages.md).

- **Every width**: `pages/ticket/TicketAgent.vue`, inside the inbox page `pages/ticket/TicketsInbox.vue` (Phase 16;
  `MobileTicketAgent.vue` is gone).
- **The customer portal is separate**: `/my-tickets/:ticketId` renders
  `pages/ticket/TicketCustomer.vue` (`TicketConversation`, `TicketCustomerSidebar`,
  `EstimateApprovalBanner`), none of which this page uses or changes.

**Phase 16 (TBO Copilot, Nov 2026): the ticket as one conversation.** The Chat / Customer / Activity tabs are gone.
The page is the ticket's header, then three parts (`components/ticket-inbox/`), re-mounted per ticket:
- **Where it stands** (`TicketStanding.vue`), always on top: whose move it is in words, with the SLA (`dueBadge`)
  while its clock runs ("Aisha is waiting for a reply, and it's overdue.", "Waiting for Aisha to answer. The SLA
  clock is paused.", "Resolved. Aisha rated it 4/5."), and Copilot's line and buttons (the Phase 11 state from
  `helpdesk.api.copilot_thread.history`: Approve, Reject, Start Copilot, Deploy…, the rest in its ⋯, and a reason
  asked first where one is needed). **Reply to Aisha** shows while the customer waits.
- **One conversation** (`TicketConversation.vue`), oldest first with day separators: the customer's emails on the
  left (white, `EmailBubble.vue`, the body in the same `EmailContent` frame, Reply / Reply all / Split ticket); our
  replies on the right (blue, "Sent to Aisha"; Copilot's own update, sent as the automation user, "Automatic update to
  Aisha"); people's notes on the right (`CommentBox`, the note colour, edit and delete as before); a person's
  question to Copilot on the right in the note colour ("To Copilot · only the team"); Copilot's messages and cards
  (`CopilotCard`, its buttons) and its own notes as wide gray cards; history, calls and the rating as small centred
  lines (folded history: "and 2 more"). Filters: **Everything**, **Customer sees** (emails, calls, the rating),
  **Team only** (notes, Copilot). A ticket made on the desk with no email of its own opens with its description.
  The newest message stays in sight while the email frames size themselves.
- **One box to write in** (`TicketComposer.vue`): **Reply to Aisha** (R; the email editor, "Use Copilot's draft"
  when one is ready), **Note to team** (C; the note editor, @mentions) and **Ask Copilot** (Q; a chat line, Enter
  sends, quick questions; people who may only read the Copilot chat see why instead). A collapsed box opens on a
  click; the open editor folds on a click elsewhere and keeps its draft. `composerMode` / `startWriting()` in
  `modalStates.ts` let the AI card, the meeting dialog and Getting started open the right mode.
- The header has no Reply button any more (the box is always there). The SLA moved from the title line into the
  summary. On a phone the header is one line (status, Details, ⋯ with the form scripts' actions) and the subject,
  the contact and the assignee are under it.
- Details is the Phase 15 panel: beside the ticket from `lg`, but a sheet below 1440px when the inbox list is beside
  the ticket (`TicketSidebar`'s `sheet` prop now decides, not the breakpoint).
- Whose message is Copilot's: `get_communications` and `get_comments` mark the automation user's emails and notes
  (`by_automation`), only when one is set up (without it `automation_user()` is Administrator, a person). A sender
  without a user account shows by the name their email gave.

**Phase 15 (TBO Copilot, Nov 2026): each fact once.** The number is in the breadcrumb; the status and the assignee
are in the header (their pickers). Under the title, one line: the contact, the customer, "via Email · opened 3 hours
ago", the priority and **one** SLA badge, what is due next (`dueBadge`, the list's Due). The ID chip, the status chip
and "Assigned to …" are gone from the title; **Copy ticket ID** is in the ⋯ menu (and ⌘. still copies it).
- The status picker and its menu show each status's icon and word in its tone (`statusBadge`), as the list does.
- **Details** shows at every width: from `lg` it hides or shows the side panel (kept per browser,
  `helpdesk-ticket-details-hidden`); below `lg` it opens the sheet.
- The assignee's name shows once (it showed twice: the avatar's label and the name).
- `[` and `]` go to the previous and next ticket, besides ⇧< and ⇧>.
- **Chat**: the Copilot line has four looks. Not started has a robot icon and Start Copilot. Working has a spinner.
  "Needs you" (amber) appears only when a person must decide (Approve, Reject, Let Copilot fix it, Build, Deploy), no
  longer for Start Copilot. A finding has the sparkle icon.
- **Customer**: "Comments" is "Internal notes" (filter and composer). When the reply box opens and Copilot has a
  draft ready, the box offers it ("Use the draft" / "Not now"); the full card with its sources and Draft again stays
  in Details → AI assist.
- **Activity**: one line per email, internal note and call ("Aisha Rahman wrote by email", "Agent added an internal
  note"), and a line opens its message on the Customer tab. Copilot's own notes keep their card there, as they are
  not on the Customer tab.
- The customer's rating shows only on a resolved or closed ticket that has one.
- **Details**: the first section is "Ticket". The customer site (session replay) follows the SLA. Empty fields read
  "Add a type", "Add a priority", and the owner "None set". The SLA summary uses the same words as the title line.
- **Phone**: the breadcrumb is "Tickets / #number"; the subject has its own line in full (Phase 16: under the
  one-line header, with the contact and the assignee).

## Header

`components/ticket-agent/TicketHeader.vue`, with the title block in `TicketTitle.vue` (teleported
into the app header).

- **Title**: the subject (a button: click to rename), then a row with `#id` in Geist Mono (click
  or ⌘. copies it; ⌘⇧. copies the URL), the status badge, the priority badge, the SLA badges and
  the channel (via Email / via Portal), then a line with the customer (links to the customer
  page), the contact and who it is assigned to ("Unassigned" otherwise).
- **Badges** come from `pages/ticket/ticketMeta.ts`, shared with the tickets list:
  - status by category: Open neutral (dot), Paused amber (pause), Resolved green (check);
  - priority: Urgent red, High amber, others neutral, always with the signal icon;
  - SLA, one badge each for First response and Resolution, only when the ticket has that
    deadline: while the clock runs, when the deadline falls ("First response: 10:30 AM",
    "Resolution: Tomorrow 10:30 AM", "Tue 2:30 PM", "13 Oct, 2:30 PM") with a clock, amber with
    at most one working hour left; Failed (red, alert), Fulfilled, Paused. Hovering, and the
    badge's screen-reader text, give the exact deadline and the working time left ("19 working
    h left"). Deadlines are set in working time, so a calendar countdown ("in 2h") overstated the
    time across nights, weekends and holidays; see
    [tickets-and-calendar-pages.md](tickets-and-calendar-pages.md) for the wording rule.
  - The working time left comes from `useSlaTimeLeft` (one request for this ticket, refreshed
    every 60 seconds and when a deadline changes). The page provides it (`SlaTimeLeftSymbol`, in
    `TicketAgent.vue`), so the summary over the conversation and the SLA panel share one
    count.
- **Actions**, right to left in importance: viewers, previous/next ticket (⇧< / ⇧>), the custom
  actions from HD Form Script, the **status** menu (S; neutral, with the status's colour dot),
  **Details** (hides or shows the panel, or opens its sheet), and the **⋯ menu** (Phase 16: no Reply here; the
  box under the conversation is always there): Create task, Schedule Teams meeting (when meetings are on),
  Merge ticket (open tickets, when there is another open ticket), and Delete (admins), plus
  grouped custom actions.

## Conversation

Since Phase 16: `components/ticket-inbox/TicketConversation.vue` (see the top of this page). The notes below are the
timeline it is built from; `TicketActivityPanel.vue` and its tabs are gone (`ticket/TicketAgentActivities.vue`
stays for other uses).

- **Timeline** built by `composables/useTicketActivities.ts`, shared by the desktop and phone
  pages: emails, comments, calls and history in time order, consecutive history by the same person
  folded, the customer's feedback last.
- **Who wrote it**: an email from the customer (`Communication.sent_or_received` = Received) is a
  white card labelled "Customer" (person icon); an agent's reply (Sent) sits on the gray-1 surface
  labelled "Agent reply" (send icon); "AI-drafted" stays as before. Comments are internal notes on
  the `note` / `note-border` tokens with the "Internal note" label (`CommentBox.vue`).
- **States**: skeleton cards while the activity loads, an error with **Retry** if it fails, and
  the per-tab empty text.
- **Composer** (Phase 16: `TicketComposer.vue`, three modes, see the top of this page; before it,
  `CommunicationArea.vue`, sticky under the timeline): a segmented Reply / Comment
  switch with their shortcuts (R / C) shown as keys; the buttons are 44px tall on phones and
  compact from `md`. Reply shows "To: …"; Comment says "Only agents
  see comments" and the editor sits on the note colour. ⌘⏎ sends, Esc closes, as before. The AI
  suggested reply's "Use this reply" and the header's Reply open the email composer
  (`openReplyBox()` in `modalStates.ts`).

## Side panel

`TicketSidebar.vue` → `TicketDetailsTab.vue`. One scroll area, sections in order of how often an
agent needs them. Every section heading is `PanelSection.vue` (eyebrow title, optional icon and
count, header actions, optionally collapsible with `aria-expanded`); the AI cards are level-3
sections inside the AI group.

1. **Details**: Type, Priority, Customer, Team as quiet selects (T, P, ⇧T open them), the
   customer's ticket owner (read-only "Customer owner", see [ticket-owners.md](ticket-owners.md))
   and the assignee (A). Status is the header's menu.
2. **Contact**: name, email, email/call buttons (with telephony), open the contact, and how many
   unresolved tickets the contact (or sender) has.
3. **SLA** (`TicketSlaSection.vue`, when the ticket has a deadline): the policy, First response and
   Resolution badges with "Due … · 30 working min left" / "Responded …" / "Resolved …" times, and
   "Paused since" while paused. The header says when each deadline falls; this has the exact
   times and the working time left. A ticket on the follow-up ladder also shows "Follow-up" with
   its `EscalationBadge` (`custom_escalation_level`, see [follow-ups.md](follow-ups.md)).
4. **Linked work** (`TicketLinkedWork.vue`): tasks raised from this ticket with their status, project,
   due date (red with an icon when overdue) and pull requests (`PullRequestChip`, open first, at most
   three). A task opens in `TaskDetailDialog` when the viewer may read it (`mine` decides which steps
   it offers). **New task** opens the page's one `CreateTaskDialog`; the header menu and the
   estimate card open the same dialog through `showCreateTask` in `modalStates.ts`. After a task is
   created, the list, the ticket (now Waiting on Task) and the activity reload. Loading skeleton,
   error with Retry, and an empty line explaining when to create one.
5. **Meetings** (`meetings/MeetingsCard.vue`, unchanged).
6. **Session replay** (when the ticket has one, unchanged apart from the heading).
7. **AI assist**, collapsible (open by default, remembered in `openedSections.ai`):
   - **Triage** (`AiTriageCard.vue`): reads the ticket's `custom_triage_*` fields, so no extra
     call. Pending ("Reading the ticket…", Check again reloads the ticket), Failed, or the summary
     (sanitised) with category, suggested priority, complexity, recommended track and when.
   - **Suggested reply** (`AiSuggestedReplyCard.vue`): as before; the draft is now rendered
     through `sanitizeRichText`.
   - **Possible duplicates** (`DuplicateTicketsCard.vue`), with the count.
   - **Customization estimate** (`CustomizationEstimateCard.vue`), status badge from `TaskyBadge`.
   Each card hides itself when it has nothing; when all do, the group says so.
8. **Ticket Info** (custom fields) and **Recent / Similar tickets**, collapsible, as before.

**Below `lg`** the panel is a modal sheet from the right (max 24rem, `role="dialog"`,
`aria-modal`) over a dim backdrop, opened by the header's Details button. While it is open, Tab
stays inside it and focus that lands on the page behind comes back (field popovers render in
`#popovers`, outside the page, so they work as usual); Esc anywhere (unless a dialog or menu above
it takes it), the close button or the backdrop close it, and focus returns to the opener. The
T / P / ⇧T shortcuts open the sheet first (`openTicketDetails`, provided by `TicketAgent.vue`),
wait a tick, then open the field. From `lg` it is inline with the resizer.

**Phones**: the Details tab renders the same `TicketDetailsTab`, so the phone page has every
section above (before, it rendered contact and feedback components that were never registered,
so contact never showed).

## API

- `helpdesk.api.work.get_ticket_linked_work(ticket)`: agents who can read the ticket. Tasks with
  `hd_ticket` = the ticket, newest first: `name`, `subject`, `status`, `project`, `project_name`,
  `exp_end_date`, `assignees`, `mine`, `can_open` (`frappe.has_permission("Task", "read")`) and
  `pull_requests` (shared `_attach_pull_requests` with My Work and the Overview). The task list
  itself is `_linked_tasks`, which `get_ticket_task_context` (the Create task dialog) uses too.
- `helpdesk.api.ticket.get_sla_time_left(tickets)`: agents only; at most 500 names
  (`MAX_SLA_TICKETS`; a list page is 20 to 100 rows, and the list sends at most the first 500
  after several "Load more", so rows past that keep a neutral badge), else a validation
  error. Reads the tickets through
  `frappe.get_list`, so tickets the agent may not read are left out of the answer. Returns
  `{name: {response, resolution}}` in working seconds, counted from now to the deadline on the
  ticket's own SLA calendar with `HDServiceLevelAgreement.calc_elapsed_time` (the same working
  days and hours and holiday list that set the deadline; hold time is already in
  `resolution_by`). A value is null when that clock isn't running (no SLA or deadline, already
  responded or resolved, or the ticket is paused) and 0 once the deadline has passed. Each SLA
  document is loaded once per request and reads its holiday list once (`get_holidays` keeps it
  on the document). Tests: `helpdesk/tests/test_sla_time_left.py`, with
  `test_utils.make_sla_calendar`.
- `helpdesk.api.ticket_area.inbox(filters, start, page_length)` (Phase 16): see
  [tickets-and-calendar-pages.md](tickets-and-calendar-pages.md).
- `get_ticket_activities`: each email also has `by_automation` (Copilot's own update) and the sender's name from the
  email when they have no user account (Phase 16).
- Everything else is unchanged: the ticket document, assignees, contact, `get_suggestion`,
  `get_possible_duplicates`, `get_estimate`, session replay, meetings and `helpdesk.api.copilot_thread`.

## Kept as they were

Routes, permissions, realtime (`ticket_update`, `helpdesk:ticket-comment`,
`helpdesk:ticket-update`, `helpdesk:ai-suggestion`, active viewers, typing indicator), every
keyboard shortcut (R, C, S, T, P, ⇧T, A, ⇧< / ⇧>, ⌘. / ⌘⇧.; Phase 16 adds Q, Ask Copilot), custom form-script actions, email
reply / reply all / split, comment edit and delete, calls, merge, delete and the subject rename.

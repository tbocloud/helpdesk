# Customer portal and knowledge base

What TBO's customers see in the helpdesk app (their tickets and the knowledge base), and the
agents' knowledge-base list and editor. Built to [ui-guidelines.md](ui-guidelines.md): calm,
neutral surfaces, the brand colour only for the primary action and the current selection, and
status colour always next to an icon and a label. Customers often use phones, so every page
works at phone width. Shared blocks (`SectionCard`, `TaskyState`, `TaskyBadge`, `NativeButton`,
`tone.ts`) are described in [workspace-pages.md](workspace-pages.md).

Every route, permission and realtime event is unchanged. Routes with `meta.public` set
`isCustomerPortal`; the chrome follows the session (`PortalRoot`), so an agent opening a
portal page keeps the agent shell.

## Navigation

`customerPortalSidebarOptions` in `components/layouts/layoutSettings.ts`: **Tickets** and
**Knowledge base**. Before, the knowledge base was only reachable through the command palette
(or as the home page with "prefer knowledge base"), so it now has a sidebar entry, for customers
and, in the Directory section, for agents (`AgentKnowledgeBase`).

The content portal (`/content-portal`, signed in by email code) and project sign-off pages
(`/project-signoff?token=…`, one link per sign-off, sent by email) are separate `www` pages with
their own sign-in, so the helpdesk portal doesn't link to them.

## Ticket status for customers

`desk/src/pages/ticket/customerStatus.ts` is the one place that turns a ticket into what the
customer sees:

- `useCustomerStatus().stage(status)`: **open** (status category Open), **awaiting** (category
  Paused and it is the status an agent's reply sets, HD Settings `update_status_to`, now sent by
  `helpdesk.api.config.get_config`), **paused** (any other Paused status, e.g. Waiting on Task,
  shown to customers as "In progress"), **resolved** (category Resolved).
- `badge(status)`: the status's customer label (`label_customer`) with the stage's tone and icon,
  for `TaskyBadge`: open is info with a dot, awaiting is amber with a reply icon, paused is neutral
  with an hourglass, resolved is green with a check.
- `firstReplyFact(ticket)` and `resolutionFact(ticket, stage)`: the SLA deadlines as the
  customer sees them. "Replied in 2h 10m" (green), "Reply by 10:30 AM" / "Resolve by Tue 2:30 PM"
  (neutral, clock; the agents' `deadlineLabel` wording, because deadlines count working hours
  and a countdown such as "Due in 3h" overstated the time; customers see the deadline only, no
  working-time figures), "Overdue" (red,
  alert icon; agents see "Failed"), "Resolved", or "Paused" while the ticket waits on the
  customer or other work. Nothing shows when the ticket has no such deadline.

## Tickets list (`/my-tickets`)

`pages/ticket/Tickets.vue`, shared with agents (see
[tickets-and-calendar-pages.md](tickets-and-calendar-pages.md)); everything here is behind
`isCustomerPortal`.

- **New ticket** is the page's primary action.
- **Columns** (`customer_portal_columns` in `HDTicket.default_list_data`): ID, Subject, Status,
  **Last updated** (`modified`, new), Priority, First response, Resolution, Team, Created.
- **Status** is the customer badge; First response and Resolution are the customer facts, with
  the exact time on hover.
- **Phones**: one two-line row per ticket: subject (bold when unseen), then status, `#id` and
  "Updated 2 hours ago".
- **Empty**: "Raise a ticket and follow every reply from our team here." with a New ticket
  button; filtered to zero keeps Clear filters.

## Ticket (`/my-tickets/:ticketId`)

`pages/ticket/TicketCustomer.vue`.

- **Header**: breadcrumbs, custom actions, and **Close ticket** as a secondary button (replying
  is the page's main action). Closing asks first ("Close this ticket?"), or opens the rating
  dialog when feedback is mandatory and the team has replied. Closing isn't optimistic: the
  button shows a loading state, the ticket reads Closed only once the server saves it, and a
  failed close keeps it open and says why.
- **Summary** (`TicketCustomerSummary.vue`): the subject as the page heading; status badge,
  `#id` and when it was opened; then **what happens next**, one sentence by stage:
  - open, no reply yet, reply deadline ahead: "We'll reply by 10:30 AM" (or "Tomorrow 10:30 AM",
    "Tue 2:30 PM", …);
  - open, no reply yet, deadline passed: "Our team has your ticket" (no "late" message);
  - open, replied: "We're working on it", with the resolution target when there is one;
  - awaiting: "We're waiting for your reply", with a **Reply** button that opens the composer;
  - paused: "On hold for now";
  - resolved: "We've marked this resolved", reply to reopen;
  - closed: "This ticket is closed", with **New ticket**.
- **Conversation** (`TicketConversation.vue`, `TicketCommunication.vue`): oldest first, one card
  per email. The support team's messages (`sent_or_received` Sent) sit on the panel surface with
  the brand name (HD Settings brand name, "TBO Support" by default) as a badge; the customer's
  own sit on gray and read "You". Attachments are listed under each message. Only
  communications are shown: internal comments are never sent to customers (`get_comments` needs
  read access to HD Ticket Comment). Email HTML is sanitised before it renders.
- **Composer**: "Write a reply", **Send reply** (Ctrl/Cmd+Enter), attachments. A failed send
  says so and keeps the draft. A closed ticket shows "can't take new replies" and a link to raise
  a new one instead.
- **Details** (`components/ticket/TicketCustomerSidebar.vue`): a side panel on desktop and the
  Details tab on phones (`inline`): ticket ID, status, raised by, first reply and resolution
  facts, priority, team and the template fields not hidden from customers; a note when the
  resolution date is more than 4 days out ("Dates follow our working hours and holidays"). The
  customer's rating, feedback and comment once given. This replaces the old phone-only
  `TicketCustomerTemplateFields.vue`, which duplicated the SLA logic.
- **Rating** (`TicketFeedback.vue`): "How did we do?", the rating and the feedback options (the
  chosen one in brand, `aria-pressed`), "Close and send rating" with a loading state; a failed save
  says so.
- Loading shows a skeleton; a ticket that can't be found returns to the list with a message
  (unchanged). The outside-hours banner, the estimate approval banner and live updates
  (`helpdesk:ticket-update`) are unchanged.

## New ticket (`/my-tickets/new`)

`pages/ticket/TicketNew.vue`, shared with agents (`/tickets/new`).

- Customers get a heading ("How can we help?") and a line on what happens next.
- **Subject** has a visible label tied to the field. Typing it searches the knowledge base
  (`components/SearchArticles.vue`, `helpdesk.api.article.search`) and lists up to five articles
  that may already answer it, each opening in a new tab so the draft stays; a link browses all.
  Searching, no match and a failed search each have their own short message. Article excerpts
  are sanitised (`sanitizeRichText`) before they render.
- The description editor opens once the subject has 3 characters (unchanged), with a prompt on
  what to include. **Create ticket** shows a loading state; a failed or invalid submit shows the
  reason under the form (agents too).
- The breadcrumb back to New ticket now points at the agent route for agents.

## Knowledge base, customers

### Home (`/kb-public`)

`pages/knowledge-base/KnowledgeBaseCustomer.vue`.

- **Search** first: "How can we help?", a labelled search field, and results inline below it
  (the same `SearchArticles`; the old popover, `SearchPopover.vue`, is removed, as results in a
  popover were cramped on phones). The query is kept in the URL as `q`, both ways: typing
  updates the URL, and a changed `q` (back, forward, a link) updates the field.
- **Browse by topic**: one neutral card per category with its article count
  (`CategoryFolderContainer.vue`, `CategoryFolder.vue`); loading skeleton, an error with Retry, and
  "No articles published yet".
- **Most read** and **Recently updated** (`SectionCard`s) from
  `helpdesk.api.knowledge_base.get_featured_articles(limit=5)`: published articles by views (only
  those read at least once) and by last change, each with its category. It reads through
  `frappe.get_list`, not `frappe.qb.get_query`, because on v15 the query builder skips
  permissions.
- "Can't find what you need? Raise a ticket", and **New ticket** in the header as a secondary
  button.

### Topic (`/kb-public/:categoryId`)

`pages/knowledge-base/Articles.vue`: the topic name (a skeleton while it loads, "Topic" if the
lookup fails or is empty) and article count, then the articles as rows
(title, excerpt, author, last update), with loading, error and empty states, and a link back to
all topics.

### Article (`/kb-public/articles/:articleId`)

`pages/knowledge-base/Article.vue`, shared with agents (`/kb/articles/:articleId`).

- The title is a heading, then the author and date; the text is set at about 70 characters a
  line (`max-w-[70ch]`, `prose-base`).
- **On this page**: for articles with three or more h2/h3 headings, a contents list beside the
  text on wide screens; it follows the reading position and links set the URL hash.
  `addLinksToHeadings` gives headings their ids, which the editor's `HeadingIds` keeps.
- **Was this article helpful?** (`ArticleFeedback.vue`): Yes and No as real buttons with
  `aria-pressed` (they were clickable icons before), "Raise a ticket" when it didn't help; a
  failed save reverts the choice and says so.
- **Related articles**: up to five other published articles in the same topic
  (`get_category_articles`), with a link to the whole topic. Only for an article in a topic: an
  article without one shows no card, and the list is only shown when it was fetched for the
  current article's topic.
- Loading shows a skeleton; an article that can't be loaded says so with Retry and a link to the
  knowledge base (a draft opened by a customer still returns to the knowledge base, unchanged).

## Knowledge base, agents (`/kb`)

`pages/knowledge-base/KnowledgeBaseAgent.vue`: unchanged features (grouped by category, New →
Category or Article, move, merge, share, delete). The status column and the article page's status
use one map, `pages/knowledge-base/articleStatus.ts`: Published (green, globe), Draft (amber,
pencil), Archived (neutral, archive). Editing an article keeps the full editor; the contents
list only shows while reading. New article's button reads **Create article** with a loading
state.

## Components

| Component | Where | What |
| --- | --- | --- |
| `customerStatus.ts` | `pages/ticket/` | customer stage, status badge, SLA facts |
| `TicketCustomerSummary.vue` | `pages/ticket/` | subject, status and what happens next |
| `TicketCustomerSidebar.vue` | `components/ticket/` | ticket facts; side panel or Details tab |
| `ArticleCard.vue` | `components/knowledge-base/` | one article row |
| `ArticleList.vue` | `components/knowledge-base/` | article rows with loading, error and empty states |
| `articleStatus.ts` | `pages/knowledge-base/` | article status badge map |

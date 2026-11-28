# Messages section (TBO Copilot phase 32)

**Status:** phase 32 built (steps 1–6), waiting for the owner's local test; not released yet. Plan: the design
repo's `phases/one-inbox-plan.md`, section 5.

TBO Support answers WhatsApp, Instagram, the Facebook Page and the website chat itself. Chatwoot (TBO Chat) stays
underneath as the connection to Meta: staff work in TBO Support's **Messages** section and don't open Chatwoot.

The Messages section is separate from **Support**:
- Support's tickets and the customers' ERP chats stay where they are.
- A Meta chat that turns out to be ERP support from a known customer moves to Support.

## Step 1: every message kept in TBO Support (built)

**Switch:** HD Chatwoot Settings → *Messages section* → **Keep messages in TBO Support** (off by default).

With the switch off, nothing changes: the bridge reads only customers' messages and WhatsApp outreach receipts.
With it on:

- **Every message is kept** as an **HD Chat Message**, one row per Chatwoot message id:
  - **what is kept:** customers' messages, the AI's replies, replies typed in Chatwoot's own screens, templates,
    private notes, and Chatwoot's activity lines;
  - **its fields:**
    - in or out;
    - who: Customer, AI, Staff (the TBO Support user with the agent's email) or System;
    - kind: Text, Template, Note or Activity;
    - the text, and the message it replies to;
    - the time, from Chatwoot's `created_at`, in the site's time zone;
    - the delivery status;
  - the same message delivered by both webhooks, or retried, stays one row (unique Chatwoot id).
- **Who sent a reply.** A reply a person writes on a chat ticket is kept the moment TBO Support posts it, with that
  person as its sender. Chatwoot's own copy of the message arrives later and keeps that sender. Copilot's stage
  lines and the resolve message are kept as the System's. (`ChatConversation.keep_posted`)
- **Delivery receipts** (message updated) move a message's status forward only: Sent → Delivered → Read. Failed
  keeps Meta's reason, for example the 24 hours having passed.
- **Files** are copied into private Files by a background job (`chat_messages.copy_files`):
  - **only from TBO Chat:** the file's address must be on Chatwoot's own host (the setting's base URL), so a message
    can never make TBO Support fetch another address;
  - **size:** at most *Largest file to keep* (25 MB by default); a bigger file keeps a note and Chatwoot's link;
  - **Instagram story mentions:** no media is kept, only a note (Meta's rule);
  - **locations:** kept as a map link.
- **The conversation's list fields** follow each new message, apart from notes and activity lines:
  - the last message and its time;
  - waiting on: Us after a customer's message, Customer after our reply;
  - unread;
  - for WhatsApp, Instagram and Facebook, when the 24-hour reply window closes.

  A message that arrives late, older than the last one, changes none of them.

**Chatwoot setup for the switch.** The account webhook must send **Message Created** (all messages, outgoing too)
and **Message Updated**. The owner sets this in Chatwoot. TBO Support never changes Chatwoot's settings.

**Code:**
- `helpdesk/chat_messages.py`;
- the bridge's `ChatwootEvent.keep_message` and `ignore_reason`;
- the doctypes HD Chat Message and HD Chat Message File;
- new fields on HD Chat Conversation and HD Chatwoot Settings.

**Tests:** `helpdesk/tests/test_chat_messages.py`.

## Step 2: a ticket for every conversation (built)

**Switch:** *A ticket for every conversation*, under the Messages section's switch (off by default). With it, two
more settings: **Front-desk team** and **Reopen within (hours)** (24).

**HD Ticket has two new fields** (`setup/install.get_custom_fields`, made by every migrate):
- **Section:** Support, or Messages;
- **Came In By:** WhatsApp, Instagram, Facebook, Website chat, Telegram, SMS and so on.

**A customer's message** (`ChatwootEvent.on_message`, `ChatConversation.open_messages_ticket`):
1. **The conversation's ticket is found or made.**
   - **The first message** makes a ticket. It is in the Messages section, on the front-desk team (whose assignment rule
     picks the person), with the first line of the message as its subject.
   - **The ticket is still open:** the message joins it. A ticket in *Replied* goes back to *Open*.
   - **The ticket was resolved within the reopen window:** it reopens.
   - **Later than that, or the ticket was Closed:** a new ticket starts on the same conversation. A new topic, a new
     ticket.
2. **The message is linked to that ticket** (HD Chat Message's ticket).
3. **The AI answers as before** while the chat is with the bot. When it decides a person is needed, it writes its
   subject and summary on the ticket (a comment) and hands over; no second ticket is made.
4. **A person's chat:** the message is kept, and nothing more happens. The chat is read in Messages, not as replies
   on the ticket.

**A Messages ticket never sets off the support machinery:**
- no acknowledgement email: the reply goes in the chat;
- no customer's ticket owner: it goes to the front-desk team;
- no triage;
- no Copilot run;
- no coordinators' or Leaders' notice.

Each hook checks the section: `HDTicket.assign_customer_owner`, `triage.auto_triage_ticket`,
`copilot.runs.on_ticket_insert` and `copilot.people.on_ticket_insert`.

**When the ticket is resolved,** the Chatwoot conversation is resolved too, without the "This has been resolved"
message: that line suits support, not a sale or a job.

**Move to Support** (`chat_messages.move_to_support`; API `helpdesk.api.messages.move_to_support` for agents who
may change the ticket) is for a Messages chat that is really a customer's ERP problem. What a Support ticket gets on
arrival runs then:
- the customer's own people;
- triage;
- Copilot;
- the coordinators' notice.

From then on the chat is the ticket's channel, as for any chat ticket:
- the customer's next messages become replies on the ticket, but not the earlier ones, which stay in Messages;
- the AI stays out;
- Copilot's stage lines reach the chat.

**Not changed:** WhatsApp outreach replies from leads still go to the ERP lead, with no ticket. With the switch off,
chats behave as before: a ticket only when the AI raises one or an agent adds the label `ticket`.

## Step 3: Support's lists leave Messages tickets out (built)

**The rule** (`chat_messages.support_only`): Support's ticket lists leave out Messages tickets, unless the filter already
names a section. A manager filtering for *Section = Messages* still sees them. A ticket from before the field, with
no section, counts as Support's.

**Where it applies:**
- the agents' Tickets list and its views, and the customer portal's list (`api/doc.get_list_data`);
- the phone app's ticket lists (`api/mobile.get_tickets`).

Agent Home lists only the person's own tickets, so it needs no change: front-desk people see their chats there, and
nobody else does.

**SLA: set up in TBO Support, no code.** Helpdesk → SLA policies → new policy **Messages**:
- condition `doc.custom_section == "Messages"`;
- response time, for example 15 minutes in office hours.

Support's tickets keep the default policy, and SLA reports can be filtered by policy.

**Reports:** Helpdesk's reports read all tickets. Filter them by **Section** (a standard filter) until the Messages
report arrives in phase 34.

## Step 4: the Messages screen (built)

**Who:** System and Agent Managers, and the members of the front-desk team, while the Messages section is on
(`chat_messages.can_use`, sent as `can_use_messages`). The menu item **Support → Messages** and the page check it,
and so does every call (`helpdesk.api.messages`). The records themselves (HD Chat Conversation, HD Chat Message)
follow the same rule through the REST API and the desk (`chat_messages.permission_query` and `has_permission` in
hooks.py): other agents get no rows; managers always may read.

**The page** (`/helpdesk/messages`; `desk/src/pages/messages/Messages.vue` and `ChatThread.vue`; desktop and phone):
- **List:**
  - views: *Mine*, *My teams*, *Unassigned*, *Waiting for us*, *AI talking* and, for managers, *All*;
  - search by name, phone, text or ticket number;
  - each row shows the channel, *AI talking*, the reply window ("Closes in 5 h" or "Window closed"), unread, and the
    last message with its time;
  - closed chats appear only under All;
  - the view and the open chat are kept in the address.
- **Chat:**
  - bubbles for the customer, the AI, staff (with their name) and internal notes (amber);
  - Chatwoot's activity lines and Copilot's stage lines, small and centred;
  - pictures inline, voice notes and videos playable, other files as links, locations as map links;
  - delivery under our messages: ✓, ✓✓, ✓✓ Read, or *Failed* with Meta's reason.
- **Header:** *I'll answer* (the AI stops; the ticket is assigned to the person if nobody has it), *Move to Support*
  (asks first, then opens the ticket), and the ticket link.
- **Reply box:**
  - a reply, or an internal note;
  - sending a reply takes the chat over from the AI;
  - Ctrl or Cmd + Enter sends;
  - **after WhatsApp's, Instagram's or Facebook's 24 hours** the reply box is locked with an explanation. Notes are
    still allowed; templates come in the next step.
- **Context column:** the contact (and whether their email or phone is verified), the customer, the ticket (status,
  team, who has it), and the contact's earlier Messages tickets.

**Sidebar:** the Messages badge counts the person's open Messages tickets. The Tickets badge no longer counts them.

**Refreshing:** the list every 15 seconds and the open chat every 10 seconds, until live updates (next step).

## Step 5: files, templates and live updates (built)

**Files from the reply box** (*Attach*):
- the person uploads files as private files, then sends them with or without text;
- `send_message(files=…)` takes only the person's own fresh uploads, at most 10, each within *Largest file to keep*;
- they go to Chatwoot as a multipart form (`ChatwootClient.post_files`);
- the message keeps them as its files, and the File records are attached to it;
- after a closed window, files are blocked like text, except in an internal note.

**WhatsApp templates after the 24 hours** (*Send a template*, WhatsApp chats only):
- the person picks one of the approved templates in use (Settings → TBO Chat → WhatsApp outreach);
- they fill its blanks, one box per `{{n}}`, and see the text before sending;
- `send_template` sends it through Chatwoot's template parameters, takes the chat over like a reply, and keeps it
  as a *Template* by that person;
- Instagram and Facebook say that a person may still answer in TBO Chat within 7 days (the human-agent tag; never
  the AI).

**Who sent it wins.** What TBO Support records about its own message (who sent it, its kind) wins over Chatwoot's
copy, also when that copy arrived first.

**Live updates:**
- each new message or delivery tick sends `helpdesk:chat-message` with only the conversation's name and whether the
  customer wrote;
- it goes to the room of HD Chat Conversation, never to the whole site. Frappe lets anyone with the Agent role join
  that room (it checks the doctype, not a record), which is why the update carries no text;
- the Messages page joins the room while it is open and reloads the list and the open chat at once;
- the old refresh runs every 60 seconds, only as a fallback.

**Notifications:** *Notify me* asks the browser's permission, and is remembered in that browser. A customer's
message in a chat the person isn't looking at shows "New message — A customer wrote in Messages", without the text.
Clicking it opens the chat.

## Step 5b: chat tickets after the 24-hour window (built)

**When it applies:** a person's reply on a chat ticket, a Copilot stage line, or the "resolved" message, for a ticket
moved to Support or raised by the AI. With the Messages section on, the bridge knows when the 24-hour window closed
(`ChatConversation.window_closed`).

**What happens after the window:**
- **WhatsApp, with a ticket update template:** the text goes as the template, filled with the customer's first name
  and the update (shortened to 200 characters, in one line). It is kept as a *Template* by its sender.
- **Without the template, or on Instagram and Facebook:** nothing is sent. The ticket gets a comment, *Not delivered
  on …*, with the reason and the text, so a person can reply by email or from TBO Chat within 7 days. Before this
  step, Meta refused such messages and nobody heard.

**Setup:**
1. In Meta WhatsApp Manager, create a Utility template with two blanks, for example *"Hi {{1}}, an update on your
   request: {{2}}"*, and wait for *Approved*.
2. Add it under Settings → TBO Chat → WhatsApp outreach (sync the templates).
3. Name it in **Ticket update template (WhatsApp)**.

## Step 6: Support → Customer chats (built)

The Support chat in each customer's ERP (the TBO Support Client app) already reached TBO Support: Copilot's chat engine
answers it and keeps every message (HDS Conversation). Until now, staff saw a chat only once its ticket existed.

**Who:** the people who work Support's tickets (System and Agent Managers, and the ERP team, `can_work_tickets`).
The menu item **Support → Customer chats** and its badge (chats waiting for a person) follow it, and so does every
call (`helpdesk.api.customer_chats`). The customer's project team sees the chat once its ticket exists, as before
(decision 14's fuller version is later).

**The page** (`/helpdesk/customer-chats`; `desk/src/pages/customer-chats/`):
- **Views:** *Waiting for a person* (the customer asked for one), *AI talking*, *Mine* (the ticket is mine),
  *Answered by the AI* (no ticket, the AI answered from the knowledge base) and *All*. Search by customer, user,
  title or ticket.
- **The chat:**
  - the customer, the AI, TBO Support's people and Copilot's stage lines;
  - cards read-only, as the customer saw them, buttons included;
  - files by name (they reach the ticket when it is raised);
  - messages to the site not delivered yet are marked.
- **Beside it:**
  - the customer, their site, the user and their roles;
  - where they were: the record, or the page, and the error they saw;
  - what the AI has gathered so far;
  - the ticket, and the customer's other open tickets.
- ***I'll answer*** (`take_over`):
  - the AI stops;
  - if there is no ticket, one is raised from the chat, without starting Copilot (the person may start it), and the
    customer's chat says the ticket is raised;
  - the ticket is the person's if nobody had it;
  - the customer's chat says "*first name* from TBO Support joined the chat".
- **Reply** (`send_reply`): it goes as a reply on the ticket, exactly as from the ticket page, so it reaches the
  customer's chat at once (and by email where the ticket page's reply would). A chat with no person yet is taken over
  first.
- **Live:** each new message of an ERP chat (`conversation._record`) sends `helpdesk:customer-chat` (the
  conversation's name and who wrote, no text) to each person who may use the page, in their own room.

**Not yet:** files from staff to the customer's ERP chat need the TBO Support Client app's next version. For now,
attach them on the ticket.

## Next steps

1. Files from staff to the customer's ERP chat (TBO Support Client app: a `chat_files` capability).

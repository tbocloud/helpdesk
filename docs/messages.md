# Messages section (TBO Copilot phase 32)

**Status:** being built, step by step. Plan: the design repo's `phases/one-inbox-plan.md`, section 5.

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

## Next steps

1. The Messages screen: list, chat, context and reply box, with Move to Support.
3. Sending files and templates, the reply window, and live updates.
4. Customers' ERP chats in Support → Customer chats.

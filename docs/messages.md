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

## Next steps

1. A ticket for every Meta conversation, in the Messages section, with the guards: no Copilot, triage, coordinator
   notice or emails for Messages tickets.
2. The Messages screen: list, chat, context and reply box.
3. Sending files and templates, the reply window, and live updates.
4. Customers' ERP chats in Support → Customer chats.

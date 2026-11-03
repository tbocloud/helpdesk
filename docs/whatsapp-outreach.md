# WhatsApp outreach through TBO Chat

**Status:** built 2026-11-02. Sales sends first messages and replies on WhatsApp from TBO Support,
through TBO Chat (our Chatwoot at chat.teambackoffice.com). TBO Support stays the system of record;
the lead and the outbox live on the ERP site (TBO Smart, its `docs/whatsapp-outreach.md` and
`hub-leads-api.md` §2.19 are the other half of this contract). Everything works without the number
connected: until then Outreach behaves exactly as before (**Open WhatsApp**, then **Mark sent**).

## How to use (staff)

1. **Leads → Outreach → Draft.** Open a message to read it.
2. A WhatsApp row shows, in plain words, **how it will go**:
   - *Goes as the approved template “tbo_intro”* with the exact text the lead will read. WhatsApp
     only allows approved message templates for a first message, so this is normal.
   - *Goes as your own words*: the lead wrote to us in the last 24 hours, so your text goes as written.
   - *You send it from WhatsApp yourself*: TBO Chat is not connected yet. Use **Open WhatsApp**,
     send it, then **Mark sent**.
3. Press **Approve**. That is all: the message goes out within a minute and the row says
   **Sending on WhatsApp**, then **Sent**, **Delivered** and **Read**.
4. When the lead replies, it appears on the lead page under **Timeline** (“The lead, on WhatsApp”).
   The reply is sorted for you like an email reply: *Interested* moves the lead forward and sets
   today's follow-up, *Not interested* closes it, *Unsubscribe* (or just “stop”) ends all messages.
5. To answer: open the lead, **WhatsApp** card.
   - They wrote in the last 24 hours: type and press **Send on WhatsApp**.
   - Otherwise the card says why and offers the approved template to send instead.
   - **Open in TBO Chat** opens the whole conversation.
6. A message shown as **Failed** says why in words. Edit it and approve again, or cancel it.

## What the owner sets up (checklist)

1. **Connect the number in TBO Chat** (Chatwoot → Settings → Inboxes → Add inbox → WhatsApp,
   WhatsApp Cloud). Needs the Meta business verification you are doing.
2. **Create the templates in Meta WhatsApp Manager** (Message templates → Create) and wait for
   *Approved*. Marketing category. One template for the first message, for example
   `tbo_intro`: *Hi {{1}}, this is TBO. {{2}}. Can we talk this week?* — {{1}} is filled with the
   lead's first name and {{2}} with the Why call line. Add a sample for each blank when Meta asks.
3. In TBO Chat, check the account webhook already points at TBO Support (the chat bridge's
   `account_webhook`, signed with the account webhook secret) and that it includes **message
   created** and **message updated**. Nothing else is needed for replies and delivery receipts.
4. In TBO Support: **Settings → TBO Chat → WhatsApp outreach**
   - **WhatsApp inbox ID**: the number in the inbox's address (`…/inbox/9`).
   - **Default country code**: 91.
   - **Send WhatsApp automatically after approval**: on (the default). Off: approved messages
     wait for the person to send them by hand.
   - **Read from TBO Chat** pulls the approved templates (this also checks the connection and says
     in words what is missing). Tick **For first messages** on the one to use, and set what each
     blank is filled with (`name`, `company`, `why_call`, in order). Templates can also be added by
     hand.
   - **Save WhatsApp settings.**
5. On the ERP site: TBO Smart Settings → Outreach → **Enable Outreach** (already needed for
   email) and the latest TBO Smart (`hub-leads-api.md` v1.19).
6. Send yourself one: draft a message for a test lead with your own number, approve it, answer it.

## How it works

- **Approving.** `helpdesk/api/outreach.py` approves as the person; when the inbox is set and
  automatic sending is on it passes `send_whatsapp=1`, so the ERP queues the message, and starts
  `whatsapp_outreach.send_pending` at once. The same job runs every minute (`hooks.py`), so nothing
  waits long and nothing is lost if a call fails.
- **Sending.** `send_pending` asks the ERP for the queue (`get_whatsapp_queue`, in the ERP's send
  window; it claims each message so it is handed out once), and for each message finds or creates
  the Chatwoot contact by phone (E.164, the default country code added to 10-digit numbers), opens
  a conversation in the WhatsApp inbox and posts either the free text (the lead wrote in the last 24
  hours) or the approved template with its blanks filled (`processed_params`). It reports back
  (`report_whatsapp`): `sent` with the text, the template and Chatwoot's ids, `failed` with the
  reason, or `manual` when there is no inbox or no template, which leaves the message Approved with
  the Open WhatsApp button.
- **Replies.** The bridge's `receive_webhook` verifies every delivery (HMAC over timestamp and
  body, five-minute replay window) exactly as for support chats. A message in the WhatsApp inbox
  is first offered to `whatsapp_outreach.on_incoming`, which sends it to the ERP
  (`receive_whatsapp`); when the number or conversation belongs to a lead the ERP files it on the
  lead and sorts it with the email reply sorter, and the support AI never sees it. A number that is
  not a lead's carries on as a support chat. If the ERP cannot be asked, the event shows as Failed
  in the event log rather than the support AI answering a lead.
- **Receipts.** `message_updated` events of our outgoing WhatsApp messages (sent, delivered, read,
  failed) go to the ERP (`whatsapp_status`).
- **Lead page.** `get_lead` adds `lead.whatsapp_box` (TBO Chat ready, the conversation link, the
  templates filled with this lead's details). `helpdesk.api.whatsapp.reply` sends from the card as
  the signed-in person: the ERP says whether they may write to the lead, whether the lead
  unsubscribed and whether the 24-hour window is open; the message is filed on the timeline only
  after TBO Chat accepted it.

## Decisions made without the owner

1. **The hub pulls and sends.** The ERP never holds Chatwoot credentials; this follows the usual
   direction (the hub calls the ERP) and survives a restart of either side.
2. **A template is chosen by rule, not by the AI.** The first message goes as the template ticked
   for first messages, filled from the lead's first name, company and Why call line. The AI's
   draft text is used only as free text inside the 24-hour window. This keeps Meta's approved
   wording intact and means a first message can never be rejected for its content.
3. **Setup gaps fall back to manual, never to a lost message**: no inbox, no template, or the
   switch off all leave **Open WhatsApp** as today.
4. **Templates are synced from Chatwoot** (the WhatsApp inbox lists its templates) and can also be
   typed by hand; one sync pass puts templates Meta no longer approves out of use.
5. **Ids**: Chatwoot's contact and conversation ids are kept on the lead (ERP custom fields), the
   message id and the template on the outreach message.
6. **Marketing category** for every template (the strictest); change it per template in Chatwoot
   if a template is Utility.
7. **Stop words.** A reply that is only “stop” or “unsubscribe” unsubscribes without the AI;
   anything longer is read by the same classifier as email.
8. **A message stuck in Sending** (the hub crashed between taking it and reporting) is not
   retried, so a lead never gets it twice; the BD cancels it or marks it sent.
9. **Contacts the support team already has** are reused (found by phone); a lead's conversation is
   a normal TBO Chat conversation, so an agent can take over there.

## Tests

`helpdesk/tests/test_whatsapp_outreach.py` (Chatwoot mocked with `FakeChatwootAPI`, the ERP site
with `FakeCRM`; helpers in `test_utils.py`): a template required outside 24 hours and free text
inside; blanks filled and neutral words when a detail is missing; the fallback with no inbox, no
template or automatic sending off; the queue sent through a new or found contact and conversation,
failure reported in words, one bad message not stopping the rest, the country code passed;
approving passing `send_whatsapp`; the outbox plan per row; a lead's reply forwarded and kept from
the support AI, other numbers staying support, the ERP being down; the webhook's HMAC (unsigned
and wrongly signed deliveries refused, replays handled once); delivery receipts; the template
sync; the settings (admin only, country code cleaned); the lead card's reply box.

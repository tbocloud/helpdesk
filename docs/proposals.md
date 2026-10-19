# Proposals

Status: built 2026-10-19 (Phases 2 to 4 of the sales flow the owner approved on 2026-10-16:
segment rate card, proposal builder, send / view / accept). This document is the source of
truth for the hub's side and changes with it.

## Why it works this way

Proposals, like leads, live on the ERP site (india.teambackoffice.com): TBO Smart's
**TBO Proposal**, priced by the lead's own ERPNext **Quotation**. The hub keeps no copy. It
builds, prices and sends them live through TBO Smart's hub proposals API as the signed-in
person, and the client reads and accepts them on the ERP site at `/proposal/<link>`, so the
price, the discount approvals and the pipeline's won path all stay in one place. The hub never
gets ERPNext installed.

The ERP side's spec is TBO Smart's `docs/proposals.md`; its contract is
`docs/hub-proposals-api.md` (and the rate card in `docs/hub-leads-api.md` §2.3).

## Who sees it

- Everyone who sees Leads (`can_use_leads`, [leads.md](leads.md)), while **Proposals** is on in
  TBO Smart Settings on the ERP site. Off there: the Lead page shows no Proposals section and
  Settings → Rates and proposals says so.
- What each person may do is the ERP site's call: a proposal opens when they may read its lead
  and changes when they may write it; templates and rates change only for the roles that edit
  quotation presets and prices there (`can_edit`, `can_edit_templates`).

## Hub endpoints

`helpdesk/api/proposals.py`, thin typed proxies (writes POST), each checking `can_use_leads`
and sending `acting_user`:

| Hub method | ERP method |
| --- | --- |
| `get_proposal_options` | `hub_proposals.get_proposal_options` |
| `create_proposal(lead, template, ai_draft)` | `hub_proposals.create_proposal` |
| `get_proposal(name)` | `hub_proposals.get_proposal` |
| `save_proposal(name, data)` | `hub_proposals.save_proposal` |
| `get_pricing_form(name)` | `hub_proposals.get_pricing_form` |
| `save_pricing(name, values)` | `hub_proposals.save_pricing` |
| `request_approval(name, reason)` | `hub_proposals.request_approval` (reason required here too) |
| `send_proposal(name, recipients, message, attach_pdf)` | `hub_proposals.send_proposal` |
| `create_revision(name)` | `hub_proposals.create_revision` |
| `upload_proposal_image(name, filename, content)` | `hub_proposals.upload_proposal_image` (`content` base64; refused here above 5 MB or when it isn't base64, before anything is sent) |
| `set_default_letter_head(letter_head)` | `hub_proposals.set_default_letter_head` (editors only, checked there) |
| `save_template(data)` | `hub_proposals.save_template` |
| `get_rate_card`, `save_rate_card(rows)`, `set_segment_rate(item_code, rate, segment)` | `hub_leads.*` of the same names |

`helpdesk.integrations.crm.leads.call(method, post, api=…)` takes the API module, so the
proposals proxies share the leads call and its error mapping ([leads.md](leads.md) "Errors
people see"): the ERP site's own reason (a refused send, a segment move, a discount above the
band) reaches the page.

Every proxy that answers with a proposal runs its `letter_head_preview` HTML through Frappe's
`sanitize_html` once more (the ERP site already did), because the preview renders it.

**Images** stay private on the ERP site (Files attached to the proposal). The builder and the
preview load them straight from the ERP site's token-gated link (`image_url`,
`proposal_page.image`), so the hub stores and proxies no image bytes except on upload, and the
API key never reaches the browser.

## The screens

### Lead page: Proposals (`LeadProposals.vue`)

Next to Quotations: each proposal with its version, views and status (Accepted green, Declined
and Expired red, Viewed blue, the rest gray, always with the word). **New proposal** (people who
may write the lead) opens a dialog: pick a template (or Blank, with its description) and, when
the ERP site has AI drafts on, **Draft it with AI**; the button says **Create proposal** or
**Draft proposal**. AI warnings (blocks left out because of numbers that aren't in the lead's
notes) show as toasts, and the builder opens. The timeline shows proposals as "<title>:
<status>" with their own icon.

### Builder (`/helpdesk/leads/<lead>/proposals/<name>`, `Proposal.vue`)

- **Header:** breadcrumb (on a phone, back to the lead), status, **Preview link** (the client's
  page in a new tab, `?preview=1`, which counts no view; icon only on a phone), **Save
  changes** ("Saved" and off until something changes), or **Create revision** once it was sent, and
  **Send** (the one primary action; **Send again** once sent). Send is off with unsaved edits
  and while the ERP site gives reasons (`send_blockers`), with the first reason as its tooltip.
- **Can't send yet:** a warning panel lists every reason in the ERP site's words (pricing above
  the limit or waiting for approval, no outgoing email account, validity passed, …).
- **With the client** (`ProposalTracking.vue`, once sent): sent on and to, views, last opened,
  accepted or declined with who and their reason, and the client's link with **Copy link**.
- **Details:** title, valid till, theme (TBO Teal or Graphite, `TabButtons`) and **Letter
  head**: "Default (<name>)" or any Letter Head on the ERP site (`letter_head`; blank: the
  default). With no Letter Head on the ERP site at all, editors see a warning instead (the page
  then shows only the company's logo).
- **Blocks** (`ProposalBlocks.vue`): ordered cards with **Move up**, **Move down** and
  **Remove** (named buttons; the keyboard stays on the block that moved), a heading and the
  text, whose placeholder is the template's guidance for that block. **Add a block** picks the
  type. A blank line starts a paragraph and "- " a list item, as on the client's page.
- **Images** (`ProposalImageField.vue`): an **Image** block (an optional heading, the image,
  **Alt text** (required), an optional caption and **Width** Full / Half) and a cover image on
  the **Cover** block. **Upload image** / **Replace** opens the file picker (PNG, JPEG or WebP
  up to 5 MB, checked in the browser first and by the ERP site by content), **Remove** takes it
  out; a thumbnail, the button's loading state and the error in words. Uploading only adds the
  file; **Save changes** puts it in the proposal.
- **Pricing block** (`ProposalPricingSummary.vue`): the lead's segment and its discount band,
  the quotation (name, status, lines, discount and total), and when it is above the limit a
  warning with **Request approval** (a reason, then the next level up decides on the ERP site
  or in the app). **Price the proposal** / **Change pricing** opens `ProposalPricingDialog.vue`:
  a package fills the lines; each line a service (priced from the segment's list), qty, rate
  and discount; the extra discount, tax and the quotation's validity; a live estimate of the
  overall discount and total, with a warning above the band. **Save pricing** saves the lead's
  quotation on the ERP site (revising it first if it was already sent).
- **Versions:** every version of the proposal, the current one marked.
- **What the client sees** (`ProposalPreview.vue`): the page drawn live from the editor in the
  chosen theme, with the saved letter head's header and footer (`LetterHeadPart.vue`; a newly
  picked one shows once saved) and the images, empty blocks left out as on the real page. Side
  by side from `xl`, stacked below.
- **Send dialog:** To (the lead's email, or where it last went), an optional message (blank: a
  standard greeting) and **Attach the PDF too**; **Send proposal**. The ERP site emails it and
  records it on the lead.
- A sent proposal is read only; **Create revision** makes the next version as a draft and opens
  it.
- States: skeleton while loading, an error with Try again and Back to the lead.

### Settings → Rates and proposals (`components/Settings/Sales/`)

For everyone who sees Leads; inputs are read only (with a note) for people who may not change
them on the ERP site.

- **Segment rate card:** each segment's price list (blank: the selling price list) and
  discount band %.
- **Service rates:** the rate of each service on the selling list or on a segment's own list
  (`TabButtons` for the list); a segment without a list of its own has nothing to edit there.
- **Save changes** saves the card and every changed rate.
- **Proposal letter head:** the default letter head (TBO Smart Settings → Proposal letter head
  on the ERP site): "The one marked default (<name>)" or any Letter Head; saved with **Save
  changes**, editors only. With no Letter Head on the ERP site, a warning says to add one.
- **Proposal templates:** the templates (disabled ones greyed) and **New template**; a template
  opens `ProposalTemplateEditor.vue`: Enabled, name, solution type, description, default
  packages and the blocks (the same block editor, with each block's guidance and default text).

## Tests

`helpdesk/tests/test_proposals.py` with `test_utils.FakeCRM` (`lead_answers`, `lead_calls`,
`lead_paths`, `lead_error`): only people who use Leads; reads GET and writes POST to the
proposals API as the signed-in person, with the arguments trimmed and typed; the rate card on
the leads API; a reason required for an approval request; the ERP site's reason reaching the
page; an image upload checked here (size, base64, Leads users only) and then posted on; the
default letter head set on the ERP site; the letter head's HTML sanitised for the preview.

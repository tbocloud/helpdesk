# Proposals

Status: built 2026-10-19 (Phases 2 to 4 of the sales flow the owner approved on 2026-10-16; the
Universal IT Proposal, the guided chat and the module library the owner set on 2026-10-19). This
document is the source of truth for the hub's side and changes with it.

## Why it works this way

Proposals, like leads, live on the ERP site (india.teambackoffice.com): TBO Smart's
**TBO Proposal**, priced by the lead's own ERPNext **Quotation**. The hub keeps no copy. It starts,
builds, prices and sends them live through TBO Smart's hub proposals API as the signed-in person,
and the client reads and accepts them on the ERP site at `/proposal/<link>` (or as an A4 PDF), so
the price, the discount approvals, the libraries and the pipeline's won path stay in one place.
The hub never gets ERPNext installed.

A proposal is **assembled, not written**: a master structure of 23 sections, a pre-written module
library and section libraries on the ERP site fill every factual section at no AI cost; one small
AI call writes the narrative. Presales should not have to type content.

The ERP side's spec is TBO Smart's `docs/proposals.md` (v2.1) and, for the documents after an
accepted proposal, `docs/client-documents.md` (v1.4); its contract is `docs/hub-proposals-api.md`
(v2.4).

**The documents after the proposal** (the owner's chain of 2026-10-19): **Proposal → Quotation →
Project Agreement / Work Order → BRD → SRS → Implementation Plan → Project → UAT sign-off**
(the UAT is the project's sign-off, [project-signoff.md](project-signoff.md) UAT). Each is a TBO Proposal of its own type on the ERP site, made from the accepted one before
it and pre-filled from it, so the same builder, preview, Share, Send, revisions and client page
serve them all. Each type has its own switch in TBO Smart Settings, off by default.

## Who sees it

- Everyone who sees Leads (`can_use_leads`, [leads.md](leads.md)), while **Proposals** is on in
  TBO Smart Settings on the ERP site. Off there: the Lead page shows no Proposals section and
  Settings → Rates and proposals says so.
- What each person may do is the ERP site's call: a proposal opens when they may read its lead
  and changes when they may write it; templates, libraries, rates and the default letter head
  change only for the roles that edit quotation presets and prices there (`can_edit`,
  `can_edit_templates`). Editors also see the AI's cost on each proposal.

## Hub endpoints

`helpdesk/api/proposals.py`, thin typed proxies (writes POST), each checking `can_use_leads` and
sending `acting_user`; each maps 1:1 to `tbo_smart.api.hub_proposals.<same name>`:

| Hub method | Notes |
| --- | --- |
| `get_proposal_options`, `get_proposal(name)`, `create_proposal(lead, template, ai_draft, scoping, requirements, client_profile, chat)`, `save_proposal(name, data)` | |
| `get_client_profile(lead)`, `read_client_website(lead, url, refresh)` | The website is read on the ERP site (guarded there) and kept on the lead |
| `get_requirements_from_lead(lead)`, `extract_requirements(lead, text)` | A blank text is refused here |
| `read_chat_answer(lead, question, text)` | An off-script chat answer; a blank text is refused here, the question capped at 300 and the text at 3,000 characters |
| `finalise_proposal(name, ready)` | 1: Mark ready, 0: Reopen |
| `regenerate_section(name, index, force)`, `regenerate_proposal(name, force)`, `chat_edit(name, message)` | `chat_edit` refuses a blank message and caps it at 1,000 characters |
| `price_from_modules(name)`, `get_pricing_form(name)`, `save_pricing(name, values)`, `request_approval(name, reason)` | A reason is required here too |
| `share_proposal(name)`, `send_proposal(name, recipients, message, attach_pdf)`, `create_revision(name)` | |
| `save_questions(name, questions)`, `share_questionnaire(name)`, `send_questionnaire(name, recipients, message)`, `apply_answers(name)` | A BRD's client questionnaire (the questions as a list; blank recipients and message trimmed) |
| `create_project_from_plan(plan)` | The hub project from an approved plan, once (see below) |
| `create_document(source, document_type)`, `get_document_chain(lead)` | The next document (`Quotation`, `Work Order`, `BRD`, `SRS`, `Implementation Plan`; anything else refused here) from the accepted `source`; the lead's chain. `get_lead` carries the chain too (`documents`) |
| `upload_proposal_image(name, filename, content)`, `use_library_image(name, image)` | Images over 5 MB or not base64 are refused here before anything is sent |
| `save_template(data)`, `set_default_letter_head(letter_head)` | |
| `get_proposal_library()`, `save_library_record(kind, data)`, `delete_library_record(kind, name)`, `upload_library_image(filename, content, data)`, `draft_library_module(module)` | Editors only (checked on the ERP site) |
| `get_rate_card`, `save_rate_card(rows)`, `set_segment_rate(item_code, rate, segment)` | `hub_leads.*` of the same names |

`helpdesk.integrations.crm.leads.call(method, post, api=…)` takes the API module, so the proposals
proxies share the leads call and its error mapping ([leads.md](leads.md) "Errors people see").
Every proxy that answers with a proposal sanitises its `letter_head_preview` HTML once more.
Images stay on the ERP site; the builder and the preview load them from its token-gated links,
so the API key never reaches the browser.

## The screens

### Lead page: Documents (`LeadDocuments.vue`)

Across the top of the lead, while at least the Quotation is switched on: each switched-on type in
order (Proposal → Quotation → Project Agreement → BRD → SRS → Implementation Plan → Project →
UAT sign-off), each with its status in words (Draft, Sent, Viewed, Accepted / Signed / Approved,
Declined, Expired, Created, or Not started), a check when accepted, a step number otherwise, and
for a priced one in progress its quotation's state ("Price: Pending Approval"). A step with a
document opens it. The **one primary button** is the next action from the ERP site: *New
proposal*, *Create quotation* / *Create project agreement* / *Create BRD* / *Create SRS* /
*Create implementation plan* (made on the ERP site from the accepted one, then opened; its
warnings shown), *Create project* (below), *UAT sign-off* (the project's Sign-off tab) or
*Continue the …* for the one in progress; the Project step opens the project and the UAT step its
sign-offs; "Every document is accepted" when the chain is done. The step it points at is
brand-outlined. One column on a phone; 44px targets.

### Lead page: Proposals (`LeadProposals.vue`)

Each proposal (the proposals only; the later documents are in the strip) with its version, views
and status (Accepted green, Declined and Expired red, Viewed blue, the rest gray, always with the
word). **New proposal** (people who may write the lead) opens the start page.

### Start: the guided chat (`/helpdesk/leads/<lead>/proposals/new`, `NewProposal.vue`)

Two columns from `lg` (stacked on a phone): the **Proposal assistant** (`ProposalChat.vue`) and the
**live summary**: the client profile (`ClientProfileForm.vue`), the requirements, the template and
the scoping form (`ProposalScopingForm.vue`), and the timeline, payment terms and AMC picks. Both
edit one state: every chat answer lands in the summary at once, and presales can click any field
to change it, or **Skip to the form** (and **Back to the assistant**) at any point.

The chat is **scripted**: its questions cost no tokens, and quick-reply chips are used wherever
the choices are fixed. It starts once the lead's profile is in, **greets with a recap** of what is
already known (website, what they do, industry, pain points, modules) and **skips every question
whose answer is known**; on a lead with a website and an industry the first question is the pain
points. In order:

1. The client's **website** (skipped when known). Only something typed like an address gets the
   URL check: "vasthubuiders" with a dot but no valid ending gets "That doesn't look like a
   website…" and stays **in the box** to fix (checked in the browser and again in the proxy).
   Anything else said here ("they need payroll and accounts") is an off-script answer (below) and
   the chat moves on. With the AI on, the ERP site reads a website into the profile; when it
   can't, its reason is shown in words. **No website** skips the read. Then what the client does
   and the industry, if still missing.
2. **Pain points**, asked outright with multi-select chips (Manual payroll, No real-time stock,
   GST filing is slow, Data in Excel; stored in English) plus a box for their own words or voice;
   **Send** takes the picks and the text together, one a line in the profile.
3. **What the client needs** (skipped when the requirements are filled) (typed, pasted or "Use the lead's notes"): kept as the requirements
   and, with the AI on, read into the form by the one extraction call (template, modules,
   customisations, users, hosting, AMC…); the assistant says what it filled.
4. **Modules** (chips, the template's or the extraction's picked; **Done**).
5. **Customisations** (one short line each, split one a line, 1 day each until set; or "None").
6. **Mobile app / data migration / integrations / source code** (chips), then which systems to
   connect when integrations is picked.
7. **Users** (chips 10 / 25 / 50 / 100 / Unlimited, or a number), **companies** (chips 1 / 2 / 3 /
   Unlimited, or a number) and **hosting** (chips). In the form each is a number with an
   **Unlimited** box.
8. **Timeline** (45 / 60 / 90 / 120 days, the suggested one marked), **payment terms**, **AMC**
   (a plan, or No AMC).
9. **Anything else** (added to the requirements).
10. Before offering Generate, the chat asks for whatever required profile field is still empty
    (industry, pain points).

**Off-script answers.** An answer that doesn't fit its question (an intent at the website step,
words where a number was asked) and **any answer in Malayalam script** go, with the AI on, to
`read_chat_answer`: one small structured call on the ERP site returns the English, the language,
and only the profile and scoping fields the text gives (the template, modules, customisations,
users, pain points…). The chat applies them over what it has (modules and customisations added,
profile fields filled only where empty), says what it took ("Got it. Modules: …"), and moves on.
Values are kept in English; the transcript keeps what was said and adds "Translated from
Malayalam: …" (or "…from Malayalam and English…") after it. With the AI off, or when the call
fails, the text stays in the box with a short note. An answer that fits costs nothing.

**Voice input** (`VoiceButton.vue`, in the chat and the builder's assistant): a mic beside the
input uses the browser's speech recognition (Web Speech API, `SpeechRecognition` or
`webkitSpeechRecognition`), English (en-IN) by default or Malayalam (ml-IN) with the EN / ML
toggle (locked while listening). The language, interim results and continuous mode are set
before `start()`; what is heard (interim text too) goes into the box through `v-model` to edit
before sending, and stays there if the answer is then refused. Its tooltip says what happens to
the audio, accurately: **"Uses your browser's speech service (Google in Chrome); nothing is sent
to TBO's servers or the AI."** It costs no tokens. The button is `aria-pressed` while listening,
shows "Listening…", and Esc stops it; in a browser without speech recognition (Safari, Firefox)
it stays disabled with a tooltip saying why.

Every way it can end without text says why, under the input (`role="alert"`):
`not-allowed` / `service-not-allowed` (the microphone is blocked for the site: allow it from the
lock icon), `audio-capture` (no microphone), `no-speech` (nothing heard), `network` (the
browser's speech service can't be reached), `language-not-supported` (switch to EN), any other
code in words with the code, a `start()` that throws, and an end with nothing heard ("Didn't catch
anything"). Stopping it yourself, or `aborted`, says nothing. A MediaRecorder recording sent for
server-side transcription (OpenAI) was considered as a fallback and left out: it would send audio
to an AI provider and cost per minute, against the privacy line above; the messages say to type
instead.

**Generate proposal** (in the chat's end and the header) creates the proposal with the transcript
and opens the builder. It keeps its normal look; while the profile's industry or pain points are
empty, "To generate, fill: Industry, Pain points" shows beside it (and at the chat's end), and
clicking either takes presales to the first missing field. With the
AI off the chat still works: chips and typed values go into the fields as they are, and "Write
… with AI" is hidden. The chat is calm: plain bubbles in the hub's neutrals, the brand only on the
picked chips and the primary button; `role="log"` with `aria-live`, every chip a button
(`aria-pressed` on multi-picks), Enter sends, keyboard reachable.

AI calls a typical proposal makes: **two** (the extraction and the narrative); **three** for a
lead's first proposal with a website (the summary is kept on the lead); none with the AI off.

### Builder (`/helpdesk/leads/<lead>/proposals/<name>`, `Proposal.vue`)

- **Header:** breadcrumb, status, **Share** (Copy link, Download PDF, Print, Preview link),
  **Save changes** ("Saved" and off until something changes) or **Create revision** once sent,
  and one primary action: on a draft **Mark ready** (off with unsaved edits and while the ERP
  site gives share blockers, the first as its tooltip); once marked, **Reopen** and **Send**
  (**Send again** once sent). Send is off while the ERP site gives reasons.
- **Mark ready** fixes the draft's content and numbers (the form turns read-only, with "Ready to
  send. The content and the numbers are fixed; Reopen to change them."); **Reopen** makes it
  editable again. The ERP site refuses any change while it is marked.
- **Saving** sends the modules and scoping with the sections; the ERP site rebuilds the data
  sections not edited by hand, follows a suggested timeline and reprices the quotation, so a
  module's price, days or fit shows in Modules & Features, the timeline, the Investment and the
  payment amounts on save. What stops the repricing comes back as warning toasts.
- **Copy link:** a sent proposal's link at once. A draft must be marked ready first, then asks
  **"Share this draft?"**: it goes out as Send does but without an email (blocked the same way,
  e.g. pricing waiting for approval), then its link is copied. A draft's link shows the client
  nothing.
- **Download PDF** (the ERP site's A4 PDF, a draft's through its preview) and **Print** (the
  client's page with the print dialog).
- **Can't send yet:** every reason in the ERP site's words. **With the client**
  (`ProposalTracking.vue`) once sent.
- **Details:** title, valid till, **Price shown** (Itemised / Consolidated), **Letter head**
  (Default (<name>) or any Letter Head; editors see a warning when the ERP site has none), about
  how many pages against the template's length guide, and for editors the AI on this proposal
  (runs, tokens, estimated cost, and about how many tokens a full regenerate costs).
- **Assistant** (`ProposalAssistant.vue`): the kept transcript and "Ask for a change" ("add
  Payroll", "make it 90 days", "remove AMC"). Each message is one small call on the ERP site that
  maps to structured changes; the reply says what changed. Off with unsaved edits; a note when the
  AI is off.
- **Client, requirements and scoping** (collapsed): the profile, the requirements, the scoping
  form and the template picks, and **Regenerate proposal** (every section again; sections edited
  by hand are kept, and a dialog offers to rebuild them too).
- **Modules** (`ProposalModules.vue`): each module's fit, days and price (a price typed is "set by
  hand"; **Use the list price** undoes it), its text (what it covers, key features: this
  proposal's copy only) with **Reset to library**, **Add a module** from the catalogue, and
  **Price from modules** (the quotation's lines).
- **Sections** (`ProposalBlocks.vue`): the 23 master sections and any Image / Custom ones, each a
  collapsible card (the AI's, custom and image ones open; data ones shut) with an **On** switch,
  "AI" and "Edited" marks, **Regenerate** (AI sections) or **Reset to library** (data sections; a
  section edited by hand asks before writing over it), move up / down and remove; a heading,
  the text (paragraphs, "- " lists, "## " subheadings, "a | b" tables, "A → B" workflows) and an
  image (`ProposalImageField.vue`: upload, **From the library** (tagged images for the section
  first), replace, remove, alt text, caption, width) on every section but the Investment and
  the Acceptance. The Investment shows the pricing summary.
- **Versions**, the **Send dialog** and **What the client sees** (`ProposalPreview.vue`: the
  cover, the contents with the parts, numbered sections and subsections, tables, workflow
  chains, the module cards, the timeline bar, payment amounts, the price itemised or
  consolidated, the signature boxes and the letter head; the ERP site's page and PDF are the
  real thing). It fits its column with no horizontal overflow at 1280, 1440 and 1920 px and at
  phone width: long words (links, emails) wrap, and a letter head's HTML with fixed widths is
  kept within it.
- States: skeleton while loading, an error with Try again and Back to the lead.

### The documents after the proposal in the builder

The same page (`Proposal.vue`) for every type, reading the type from the options
(`document_types`): a quotation or an agreement has no assistant, no client and scoping form and
no module editor (they keep what they copied); its sections are its type's (`section_types`, the
agreement's Parties, Purpose, Change Requests, Intellectual Property, Confidentiality and
Termination added to the block labels); the preview's cover shows the type ("Quotation",
"Project Agreement"), no part titles, and no contents for a quotation, with the type's default
headings. A quotation is priced here (the pricing dialog, *Price from modules*, *Request
approval*); an agreement shows the accepted quotation's price read only and has a **Project start
date** (Send says to set it; saving a new one dates the timeline and the purpose on the ERP site,
unless they were edited by hand). The status reads "Signed" for
an accepted agreement.

### The BRD's client questionnaire (`DocumentQuestionnaire.vue`)

On a BRD, above its sections: the questions for the client by section, how many are answered,
each answer with "New" (info) or "In the BRD" (success), and questions the AI asked marked so. On a
draft, presales rewords, removes or adds questions (a section and a question) and saves them;
answered questions can't be changed. **Share with the client** copies the questionnaire's own link
(it shows only the questions, never the draft) or sends it by email from the ERP site. When the
client has sent new answers, the primary **Update from n new answers** rebuilds only the sections
they belong to (the ERP site rewrites the narrative ones in one small AI call) and says which.
Closed once the BRD is approved, declined or revised.

### The project page

A project made from a plan (`custom_crm_lead`) shows the same Documents strip above its overview,
read only (no next action: the lead is where the documents are worked), for people who use Leads;
anyone else doesn't see it (`get_project_detail` returns `crm_lead`).

### The project from the plan (`create_project_from_plan`)

With the plan approved, *Create project* reads the plan from the ERP site and makes the hub's own
project once, through the existing project creation (`tasky.api.create_project`, so the creator is
its manager): named "<client> - <solution>" (numbered when the name is taken), the plan's start and
go-live, the client when an HD Customer has its name, the project type from the solution
(ERPNext → ERP Implementation, mobile → Mobile App, website → Website); then a task for each
phase's deliverable and a milestone task at each phase's end, each in its phase
(`custom_phase`) with the phase's dates. The project keeps the lead and the plan
(`custom_crm_lead`, `custom_crm_plan`), and the plan is told its project (`link_project`), so the
chain moves on. Pressing it again finds the same project (by the plan) and adds nothing. After
that the project is where the work is planned; changing the plan doesn't change it.

### The SRS in the builder

An SRS has a **Module Specification** section a module, headed by the module's name (and one for
the customisations), with its numbered requirements (FR-ACC-01 …) and acceptance criteria as a
table; regenerating one is one small AI call for that module on the ERP site, *Reset to library*
none. The module library editor has each module's SRS text (requirements "requirement | how the
client accepts it", roles, screens and fields, validations, notifications).

### Settings → Rates and proposals (`components/Settings/Sales/`)

For everyone who sees Leads; read only for people who may not change it on the ERP site.

- **Segment rate card**, **Service rates**, **Proposal letter head** (as before).
- **Proposal templates** (`ProposalTemplateEditor.vue`): name, solution type, description, length
  guide, the **scoping questions** it asks, its **default modules**, the default packages and the
  sections (on or off, with each one's guidance).
- **Module catalogue**, **Section libraries** and **Proposal images**
  (`ProposalLibrarySettings.vue`): each record edits in a dialog. A module: name, usual fit,
  effort, default price, Item, image tag, what it covers, key features, scope ("Subsection |
  line"), deliverables, assumptions, out of scope, workflow, solution types, enabled, and **Draft
  with AI** (fills the text once for review; nothing is saved until Save). A library item: its
  library (company overview, solution components, scope, workflows, architecture, deliverables,
  phases, timeline templates, roles, investment notes, payment terms templates, warranty, AMC
  plans, assumptions, out of scope, risks, terms, agreement clauses), title, text, subsection (an
  agreement clause: its section), days, yearly price,
  condition, order, solution types, enabled. An image: upload (PNG, JPEG, WebP up to 5 MB),
  title, alt text, the sections and modules it suits.

## Tests

`helpdesk/tests/test_proposals.py` with `test_utils.FakeCRM`: only people who use Leads; reads GET
and writes POST to the proposals API as the signed-in person, with the arguments trimmed and
typed; the rate card on the leads API; a reason required for an approval request; the ERP site's
reason reaching the page; an image upload checked here and then posted on; the default letter
head; the letter head's HTML sanitised for the preview; the start flow (profile, website read,
lead notes, extraction, create with scoping, requirements, profile and chat; a blank text
refused); regenerate, chat edits, pricing from modules, share, library images and the library
methods posted with their arguments; a library image over 5 MB refused here; the documents after
the proposal (`create_document` posted with its source and type, an unknown type refused here,
`get_document_chain` read); Mark ready / Reopen and the off-script chat answer posted with their
arguments, a blank answer refused here; the BRD's questionnaire methods posted (questions as a
list, a non-list refused here, blank recipients dropped).

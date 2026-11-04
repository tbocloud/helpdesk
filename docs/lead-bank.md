# Lead Bank

**Status:** built 2026-11-04. ERP side and contract: TBO Smart's `docs/lead-bank.md`,
`docs/commission.md` section 7 and `docs/hub-leads-api.md` section 2.22 (v1.22). Summary in
[leads.md](leads.md#lead-bank-staff-collect-leads-referral-commission).

Every staff member can add a lead by taking a photo of a shop board, visiting card, banner or ad.
The AI reads it, fills a short form, and Submit creates the lead on the ERP site, credited to the
collector. When that lead is won and the client pays, the collector earns a referral. Most
collectors are designers, developers and coordinators, not salespeople, so it is one big button, a
photo and Submit, in plain words, on the phone first.

## How to use (staff)

1. Tap **Add a lead**. It is on **Home** (top right), in the menu, and on the phone's home screen
   icon (press and hold the TBO Support icon, then Add a lead).
2. Tap **Take a photo** of the board, card or ad, or **Choose from gallery**. You can add up to five
   photos of the same business.
3. Wait a few seconds: "Reading the photo". The form fills itself in. Fix anything that is wrong
   and add what is missing. India, UAE or KSA is chosen from the phone number or your location;
   change it if it is wrong.
4. Press **Submit lead**.
   - "Thank you! We have your lead": done. Our team will call them.
   - "This business is already in our leads": someone added it before you. Whoever added it first
     keeps the credit; your note is added to the lead.
5. **My leads** lists what you added: the date, where it stands (New, Being called, Meeting, Won,
   Not interested) and what you earned or what is on the way.

If the photo can't be read, you type the same form yourself. Nothing is lost.

You earn when the lead becomes a client **and pays**: 2% of what they pay for India, 3% for UAE and
KSA, up to 25,000 per lead. It is on your monthly commission statement, like sales commission, and
is paid when management approves and pays the statement. You will never see the CRM, other people's
leads or any money except your own.

## The owner's setup

1. **Turn on Leads** in Settings → CRM (the Lead Bank follows that switch) and make sure the CRM
   user sync has given everyone a user on the ERP site (**Sync users**).
2. **AI key for reading photos.** Settings → AI providers needs a provider whose model **can read
   images**: OpenAI (for example `gpt-4o`, `gpt-4.1` or `gpt-4o-mini`) or Anthropic (any current
   Claude model). A text-only model (for example Kimi's K2) refuses the photo, and the
   collector then types the form. The Home page's AI banner tells
   you when no provider works. Each photo set costs one AI call, and one person can read 60 sets an
   hour.
3. **Referral rates, cap and departments:** Settings → CRM → Commission plans → **Referral (Lead
   Bank)**. Defaults: India 2%, UAE 3%, KSA 3%, cap 25,000 per lead.
4. **Departments per region.** India goes to the department called **TBO** until you pick another.
   Make the **UAE** and **KSA** departments in Settings → CRM → Lead departments when those teams
   exist, then pick them in the same Referral card. Until then those leads wait in a list on the
   Team page and the Sales Managers and TBO Management are notified.
5. **Managers' dashboard:** Lead Bank → Team (Sales Manager, System Manager, TBO Management).
6. **Statements:** Leads → Commission → Generate drafts as usual; referral lines appear in the
   collector's statement.

## What it is made of

| Screen | Route | What it does |
| --- | --- | --- |
| Add a lead | `/lead-bank/new` (`LeadBankAdd.vue`) | photos, the filled form, Submit |
| My leads | `/lead-bank` (`LeadBank.vue`) | the big Add button, the collector's totals and leads |
| Team | `/lead-bank/team` (`LeadBankTeam.vue`) | managers: the month by region and collector, conversion, referral due, the waiting list, **Move credit** |
| Referral (Lead Bank) | Settings → CRM (`ReferralSettings.vue`) | rates, cap, departments |

- **Backend:** `helpdesk/api/lead_bank.py` (thin proxies plus `scan_photos`), `helpdesk/lead_bank.py`
  (the photo reading), `helpdesk.integrations.crm.leads.can_use_lead_bank`, and
  `ai_engine.call_haiku(..., images=)`, which sends the photos to OpenAI (data URLs) or Anthropic
  (base64 blocks).
- **Access:** `can_use_lead_bank` is in `get_user` as `can_use_lead_bank`. `LEAD_BANK_ROUTES`
  (`pages/content/contentTeam.ts`) is added to the Sales Employee and Content Team allow lists, so
  no wall hides it; the router sends anyone without it Home.
- **The phone:** the photo inputs use `accept="image/*" capture="environment"` (the camera) and a
  second one for the gallery, as the lead photos do. The location is the lead's place (a Maps link
  and its pin). The app's manifest has an **Add a lead** shortcut, so long-pressing the installed
  icon opens the form. Photos are shrunk in the browser (`preparePhoto`, 2000 px JPEG) and sent to
  the hub twice: to be read, then to be saved on the lead.

## Decisions

- **The AI is the hub's** (`ai_engine`, its providers and failover); the ERP site never holds an
  AI key for this. Reading is a convenience: any failure becomes a sentence and the empty form.
- **Nothing the AI says is trusted:** fields are cut to length, phones must look like phones, the
  email must look like an email, and unknown keys are dropped. Text in a photo is told to be data.
- **A repeat submission can still be sent.** The scan warns early; Submit then adds the note to the
  existing lead.
- **The region is a plain three-way choice** (India, UAE, KSA), not a country picker. Detection
  fills it; the person's pick wins.
- **A separate permission path** (`can_use_lead_bank`, and on the ERP site no sales role needed):
  the Sales wall and Leads gating are untouched.

## Not built

A push to the collector when their lead is won (My leads shows it); editing a submitted lead
(managers do that on the lead page); an offline queue for photos taken without a signal.

## Tests

`helpdesk/tests/test_lead_bank.py` (the AI mocked, `test_utils.ai_reading`, `make_jpeg_photo`):
who may use it (a Digital team designer, a DM Employee and a Sales Employee may; Leads off, an
inactive agent and a non-agent may not; every endpoint refuses); a photo becomes the filled form
(company, contact, phones, cleaned email, address, state); the AI receives the photos as images and
the ERP site the phones and position; the region from the phone and the duplicate warning; the AI
cleaned (length, phones, email, unknown keys); an AI that is off, failing or finds nothing still
leaves the form; the ERP site down does not stop the reading; photo checks and the hourly limit;
submit and the other calls sent as the person to the right API; an older ERP site and the
managers-only and missing-account messages; the OpenAI and Anthropic vision messages.
The ERP site's tests cover region detection, the first collector keeping the credit, a collector
seeing only their own leads, the Sales Employee owner earning nothing, the cap and approved months.

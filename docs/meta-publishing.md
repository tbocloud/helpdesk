# Publish to Meta (Facebook and Instagram)

TBO is also a digital-marketing agency. From the content calendar, a client-approved post
can be pushed straight to the client's Facebook Page and Instagram account, with the
official Meta Graph API. **Phase 1** is organic posting. **Phase 2** is paid: a published
post can be boosted as an ad, see [Phase 2: boost and ads](#phase-2-boost-and-ads).

## The flow

1. A System Manager creates the Meta app once and saves it in **Settings → Meta**.
2. Per client, on their project, the **Meta** tab (next to Credentials): **Connect Meta**
   opens Facebook's login, the client's Page admin allows posting, and the person picks
   the Page in the hub. The hub keeps that Page's token, encrypted.
3. On the content calendar, an **Approved** or **Scheduled** post of that client has
   **Publish to Meta** in its footer: pick Facebook / Instagram, then **Publish now** or
   **Schedule**. The hub posts it and writes the live link back to the post, which becomes
   **Published**.

## Who may

- **Settings**: System Managers only (`HD Meta Settings`).
- **Connect, disconnect, publish, schedule**: `can_handle_credentials(project)`
  (`helpdesk/tasky/permissions.py`), the same rule as the client's logins: System Managers,
  the project's managers and lead, the heads of its department (Digital Marketing Head).
  Never project members, coordinators or Sales Employees. The server checks it; the UI
  only hides what you can't use.
- The doctypes themselves are System Manager only; the API works as the system after the
  check, so tokens are never readable through the desk.
- No endpoint returns a token. The sign-in token exists only between "Allow" and "Use this
  Page", then it is deleted.

## Data

| Doctype | What |
| --- | --- |
| **HD Meta Settings** (single) | `enabled`, `app_id`, `app_secret` (Password), `graph_api_version` (default `v25.0`), `redirect_url` (read-only) |
| **HD Meta Connection** | One per project (named by the project): `customer`, `facebook_page_id`, `facebook_page_name`, `page_access_token` (Password), `instagram_user_id`, `instagram_username`, `connected_by`, `connected_on`, `status` (Pending / Connected / Expired / Error), `last_error`, `granted_scopes`, `user_access_token` (Password, only while Pending) |
| **HD Content Publish** (child of the post, `meta_publishes`) | One row per target: `target`, `status` (Queued / Publishing / Published / Failed), `publish_kind`, `publish_at`, `attempts`, `next_try_on`, `meta_post_id`, `permalink`, `published_on`, `error`, `link`, `queued_by` |
| **HD Content Post** | `meta_publish_on`: when the hub will post it (the calendar's "Auto-publish" indicator) |

A post finds its connection through the customer's content project (`content_project_for`),
else any Connected connection of the same customer.

## Graph API version

One default constant, `DEFAULT_GRAPH_VERSION = "v25.0"` in `helpdesk/integrations/meta/graph.py`
(Meta lists v25.0 as supported until July 2028), overridden by **Settings → Meta → Graph API
version**. To upgrade, change the setting; nothing else is edited.

## Connecting (OAuth)

`helpdesk/integrations/meta/connect.py`, `helpdesk/api/meta.py`.

1. `start_connect(project)` returns Facebook's dialog URL with the scopes below and a signed
   `state` (HMAC under a key derived from the site's encryption key; names the user and the
   project; valid 10 minutes).
2. Facebook sends the browser to `/api/method/helpdesk.api.meta.oauth_callback`. It works only
   for the same signed-in person the state names (CSRF), and only if they still may handle
   the project's accounts. The code is exchanged for a token, then for a **long-lived** one;
   `me/permissions` must show every scope granted, else the missing ones are named.
3. The browser lands on `/projects/<project>/meta`. The person picks a Page (only Pages
   they can post to; the answer has no tokens). `select_page` stores that Page's token
   (a Page token from a long-lived user token doesn't expire), the linked Instagram
   account, and deletes the sign-in token.
4. A Graph error 190 (token expired or revoked, a changed Facebook password, the client
   removing the app) marks the connection **Expired**; **Connect again** repeats the flow.
5. **Disconnect** deletes the connection and its tokens (it does not revoke the app on
   Facebook: the client can remove it there too).

Scopes: `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
`instagram_content_publish`, `business_management` (`SCOPES`). With **Enable ads** on in the
settings, `ADS_SCOPES` (`ads_management`, `ads_read`) are asked for too (`connect.scopes()`);
clients without ads keep exactly these Phase 1 ones.

## Publishing

`helpdesk/integrations/meta/publisher.py` (queueing, retries, state) and `flows.py` (the
Graph calls).

- **What goes out**: the post's images and videos (attachments, oldest first; documents and
  design files are ignored) and its caption: Sub copy as plain text (the copy line when
  empty) plus hashtags. Format is derived: no media = text post; 1 image; 1 video =
  Video / Reel; 2 to 10 images = carousel; **Story** (Instagram) is a checkbox when there is
  exactly one media. A mix of images and video, or more than 10, is refused with the reason.
- **Instagram**: create a container (`image_url` / `video_url` with `REELS` / `STORIES` /
  `CAROUSEL` with child containers), poll `status_code` until `FINISHED` (videos; errors and
  `EXPIRED` are reported), then `media_publish`. Before starting it reads
  `content_publishing_limit` and refuses with "Instagram's daily limit of N posts … is used
  up" when the quota is spent. Only JPEG images are accepted by Instagram: PNG and WebP are
  refused with "Convert x to .jpg" (Facebook takes them).
- **Facebook**: `/photos` (one image), `/photos` unpublished then `/feed` with
  `attached_media` (several), `/videos` with `file_url`, `/feed` (text, optional link).
- **Media reachability**: Meta fetches media itself, so each file is served through
  `helpdesk.api.meta.media?token=…`, a guest endpoint that works only with a token the hub
  signed for that one File, expiring in an hour, and only for files attached to an HD
  Content Post. Files are never made permanently public. The site must be reachable from
  the internet over HTTPS for Meta to fetch them (a local bench can't publish).
- **When**: **Publish now** queues and runs a background job at once. **Schedule** picks a
  date and time (default: the post's planned time) and sets the post to **Scheduled**;
  the scheduler (`publish_due`, every 5 minutes) sends what is due. A row is claimed under a
  row lock (Queued to Publishing), so nothing is sent twice. **Cancel scheduled posts** takes
  queued targets off (a post already being sent can't be stopped).
- **Retries**: a temporary error (network, Graph 5xx, codes 1, 2, 4, 17, 32, 341, 368, 613)
  waits 5 minutes, then 15, with three tries in all. Anything else fails at once. The call
  that makes something public is never retried after a network timeout, because Meta may
  have posted: the row fails with "Check the page before trying again". A row left
  Publishing for 30 minutes (a dead worker) is freed as Failed the same way.
- **On the final failure** the post's owner, its digital marketer and the Digital Marketing
  Head(s) get a notification (`notify_users`) with the target and Meta's reason.
- **Done**: when every target is Published the post becomes **Published**, with
  `published_url` set to the Facebook link, else the Instagram one, and a line on its
  timeline. If only some targets succeeded the post stays Scheduled / Approved and the failed
  one can be tried again from the dialog.
- A post that is no longer Approved / Scheduled when its time comes (sent back, cancelled)
  fails with that reason.

## UI

- **Settings → Meta** (`components/Settings/Meta/MetaSettings.vue`): Enabled, App ID, App
  Secret (masked, **Test the app**), Graph API version, the redirect URL to copy.
- **Project → Meta** tab (`pages/tasky/ProjectMeta.vue`, same tab rule as Credentials):
  not set up / not connected / pick a Page / connected (Page, Instagram, who and when) /
  expired, with Connect again and Disconnect (asks first).
- **Post → Publish to Meta** (`pages/content/components/MetaPublishPanel.vue`, opened from the
  card footer through `EntryActionDialog`, action `meta`): connection chip, a note saying why
  it is disabled (not connected, not approved, no permission), targets (default from the post's
  platforms), the format and caption that will go out, **Now / Schedule** with date and time,
  and a status chip per target (Queued, Publishing, Published with a link, Failed with the
  reason). It looks again every 5 seconds while something is queued or publishing.
- **Calendar**: a scheduled post shows **Auto-publish <time>** on its card (Board) and in
  its Calendar-view title.

## Owner setup checklist

1. Go to developers.facebook.com, **Create app**, type **Business**. Use TBO's own Meta
   Business portfolio.
2. **App settings → Basic**: add the privacy policy URL, app icon, category. Copy the **App ID**
   and **App Secret**.
3. **Add products**: **Facebook Login for Business** (or Facebook Login) and **Instagram API**
   (the Instagram Graph API with Facebook Login for Business).
4. **Facebook Login → Settings → Valid OAuth Redirect URIs**: the redirect URL shown in
   Settings → Meta (`https://<hub>/api/method/helpdesk.api.meta.oauth_callback`). Turn on
   Client and Web OAuth login, Enforce HTTPS.
5. **Roles**: add the people who will test as Testers or Developers. Until App Review passes,
   only they (with the client's Page admin also added as a tester) can connect.
6. In the hub, **Settings → Meta**: paste App ID and App Secret, leave the version, switch
   **Enabled** on, save, **Test the app**.
7. **Business Verification** (Business settings → Security centre) for TBO's business: needed
   for Advanced Access.
8. **App Review**, one request per permission, each with a screencast (below):
   `pages_show_list`, `pages_read_engagement`, `pages_manage_posts`, `instagram_basic`,
   `instagram_content_publish`, `business_management`. Then switch the app to **Live**.
9. Per client: on their project, **Meta → Connect Meta**.

### Screencast notes for App Review

Record the hub in a test account, one video per permission is fine; all of them can share
one walkthrough, narrated, in English, 2 to 4 minutes, showing the live site on HTTPS:

1. Project → Meta → **Connect Meta**: Facebook's permission dialog with each permission
   listed, **Continue**, then the Page list in the hub (`pages_show_list`,
   `pages_read_engagement`: used to list and read the Pages and their linked Instagram
   account).
2. Pick the Page: connected state (`business_management` is requested so a client's Page
   owned by a Business portfolio can be listed; say so in the form).
3. Content calendar → an approved post → **Publish to Meta** → Facebook → **Publish now** →
   open the live post on Facebook (`pages_manage_posts`).
4. The same for Instagram: image, carousel, Reel (`instagram_basic`,
   `instagram_content_publish`), opening the result on Instagram.
5. Say plainly that the hub only publishes posts the client and the Digital Marketing Head
   approved, and never reads private messages.

## What clients need

- A Facebook **Page** (not a personal profile).
- An Instagram **Business or Creator** account **linked to that Page** (Page settings →
  Linked accounts). Without the link only Facebook works.
- The person who connects must be a **Page admin** (or have full control) on the Page and
  must tick the Page in Facebook's dialog. If the Page belongs to a Business portfolio, they
  need access there too.
- The client's admin can remove the app any time (Facebook → Settings → Business
  integrations); the connection then shows Expired.

## Limits

Meta changes these; the hub only enforces the ones it can read from the API. Check Meta's
current Content Publishing documentation before quoting numbers to a client.

- Instagram has a rolling 24-hour quota of API-published posts per account; the hub reads
  the real quota and total from `content_publishing_limit` before every post and refuses
  with a clear message when it is used up. JPEG images only. Carousels are 2 to 10 items
  (the hub sends images only). Stories carry no caption through the API.
- Facebook videos are fetched by Meta from the signed link, so the link must stay valid for
  the whole transfer (an hour).
- Media files are read into memory when served; keep videos reasonable.
- Meta may reject media it can't fetch or doesn't like; the reason is shown on the row.

## Not in Phase 1

- Facebook Stories, Instagram mixed image/video carousels, first comments, tagging.
- Reading comments back (insights for boosts are read in Phase 2).
- Deleting a post on Meta from the hub.

## Phase 2: boost and ads

A **Published** post that has a Facebook or Instagram id can be boosted from the content
calendar. Code: `helpdesk/integrations/meta/ads.py` (all the logic), `helpdesk/api/meta_ads.py`
(the endpoints). It reuses Phase 1's `GraphClient` (pinned version, no token in errors),
`connect.py` (the one scope list), the connection per project, the stored `meta_post_id` as the
ad creative, and `can_handle_credentials` for who may handle a client's accounts.

### How staff use it (how-to)

1. **Once per client** (project manager or Digital Marketing Head): project, **Meta** tab,
   **Connect Meta** (or **Reconnect Meta to allow ads** if it was connected before ads), tick
   everything on Facebook's screen. Pick the Page, then **pick the client's ad account**. The
   page shows its currency and whether it is Active. Below it is the **monthly limit**.
2. **Boost a post**: content calendar, a Published post, **Boost this post**. One window:
   - **What do you want?** More reach, More engagement, More messages or More website visits.
   - **Budget**: per day or total, in the ad account's currency. Starts as 500 a day for 5 days.
   - **Starts / Ends**.
   - **Who sees it** (folded away): places (starts as Kerala for Indian clients, the UAE for UAE
     clients, else the client's country), ages 18 to 55, optional interests (search by word),
     and Meta's Advantage+ audience, on.
   - The grey **summary** says what it will cost and reach, e.g. "₹2,500 total · 5 days · Kerala,
     18–55 · estimated reach 12,000 to 35,000 people a month", and how much of the month's
     limit is left.
3. The button says **Start boost** if you may spend, or **Ask for approval** if you only edit
   content. Approval: the Digital Marketing Head gets a notification and presses **Approve and
   start** (or **Reject**) on the post's Boost section or on the project's **Ads** tab.
4. **Follow it**: the post shows a **Boosted** chip on the board and calendar; the project's
   **Ads** tab lists every boost with status, budget, spent, people reached, results and cost
   per result, and this month's planned spend against the limit. Numbers refresh every hour.
   **Pause**, **Resume** and **Stop boost** are on each boost.
5. If it didn't run, the red line says why in plain words (payment method missing, no access to
   the ad account, Meta didn't approve the ad and the policy it broke). Fix that and boost again.

### Who may

| Person | Boost this post | Start / approve / pause / stop | Ads tab | Change the limit |
| --- | --- | --- | --- | --- |
| System Manager | yes | yes | yes | yes |
| Project manager / lead of the project | yes | yes | yes | no |
| Digital Marketing Head | yes | yes | yes | yes |
| Anyone who can edit the post (DM Coordinator) | prepares, **asks for approval** | no | no | no |
| Project member, DM Employee | no | no | no | no |
| Sales Employee | sees nothing | no | no | no |

The rule for spending is `can_handle_credentials(project)`, so nobody who is not trusted with
the client's logins can spend their money. The server checks every call.

### Safety

- **Created PAUSED, switched on last.** Campaign, ad set and ad are all made `PAUSED`; the ad,
  ad set and campaign are set `ACTIVE` only after the cap check and approval. A failure leaves
  paused objects, which cost nothing.
- **Monthly cap** (`HD Meta Connection.monthly_ad_cap`, default 10,000 in the account currency;
  only a System Manager or the Digital Marketing Head changes it). A boost counts at its most it
  can spend (the total, or the daily budget times the days) in the month it **starts**; a
  finished or stopped one counts what it really spent. A boost that would take the month past
  the cap is refused with the amount left, at the dialog, at the request and again at approval,
  under a lock on the connection so two boosts can't both squeeze in.
- At most 30 days a boost, one live boost per post and network, no past start dates.
- **Timeline**: every request, start, pause, resume, stop, rejection and failure is a comment on
  the project.
- **Billing** stays on the client's ad account; the hub never touches payment.
- **Stop** archives the campaign on Meta, so it can't be switched back on from there.

### What is created on Meta

Marketing API, Graph `v25.0` (the setting), all under `act_<ad account>`:

| Call | Notes |
| --- | --- |
| `POST /campaigns` | `objective` an outcome-based one: More reach `OUTCOME_AWARENESS`; More engagement and More messages `OUTCOME_ENGAGEMENT`; More website visits `OUTCOME_TRAFFIC`. `special_ad_categories=[]`, `is_adset_budget_sharing_enabled=false`, `status=PAUSED` |
| `POST /adsets` | `optimization_goal` `REACH`, `POST_ENGAGEMENT` (destination `ON_POST`), `CONVERSATIONS` (destination `MESSENGER`, or `INSTAGRAM_DIRECT` for an Instagram post), `LINK_CLICKS` (destination `WEBSITE`); `billing_event=IMPRESSIONS`, `bid_strategy=LOWEST_COST_WITHOUT_CAP`; `daily_budget` or `lifetime_budget` in minor units (paise, cents; whole units for JPY and the like); `start_time`, `end_time`; `targeting` with `geo_locations`, ages, optional interests and `targeting_automation.advantage_audience`; no placements, so Meta chooses; `promoted_object.page_id` for engagement and messages |
| `POST /ads` | `creative` is the existing post: `object_story_id` (the Facebook post id) or `source_instagram_media_id` + `instagram_user_id`. No new media is made |
| `POST /<id>` `status=ACTIVE` | ad, ad set, campaign, in that order |
| `GET /search?type=adgeolocation` and `adinterest` | places and interests in the dialog |
| `GET /act_<id>/delivery_estimate` | the reach estimate; if Meta can't give one the summary just leaves it out |
| `GET /<ad id>` and `/<ad id>/insights` | status, review feedback, spend, reach, impressions, clicks, actions (hourly) |

The objectives and destinations follow Meta's outcome-based (ODAX) campaign structure
(Marketing API > Campaign, Ad Set reference). **Verify against the current docs before App
Review**: Meta changes parameter names between versions, and this build could not be run against
the real API (it is tested with a mocked Graph).

A result is: reach for More reach; `post_engagement` actions; `onsite_conversion.messaging_conversation_started_7d`
actions; `link_click` actions.

### Data

| Doctype / field | What |
| --- | --- |
| **HD Meta Settings** `ads_enabled` | The "Enable ads" switch (Settings → Meta → Paid ads) |
| **HD Meta Connection** | `ads_allowed` (the client allowed the ads permissions), `monthly_ad_cap`, `ad_account_id`, `ad_account_name`, `ad_account_currency`, `ad_account_status`. `user_access_token` (Password, encrypted) is now **kept** when ads are allowed (about 60 days; it is what ads act under) and deleted otherwise |
| **HD Meta Boost** | project, customer, post, target, goal, budget type and amount, dates, days, `total_budget`, `audience` (JSON), `campaign_id`, `adset_id`, `ad_id`, `status` (Draft, Pending approval, Active, Paused, Completed, Failed, Rejected), `failure_reason`, `meta_status`, requested/approved by, `spend`, `reach`, `impressions`, `clicks`, `results`, `cost_per_result`, `last_synced`. System Manager only; the API checks access first |
| **HD Content Post** `meta_boosted` | Drives the Boosted chip |

`helpdesk.integrations.meta.ads.sync_active_boosts` runs hourly for Active and Paused boosts.
It follows Meta: a pause made in Ads Manager shows as Paused, a disapproved ad becomes **Didn't
run** with the policy reason, an archived or past-end boost becomes **Finished**. A token error
(190) marks the connection Expired, and the page says **Reconnect Meta to allow ads**.

### Decisions made for the owner

- **Spend rule**: same as client credentials (`can_handle_credentials`), not a new role.
- **Editors** draft and ask; the Head (or a manager) approves. Anyone who may spend and presses
  **Start boost** is the approver too, so there is no second click for them.
- **Cap counted by start month**, at the full possible spend until the boost ends. Simple and
  never under-counts.
- **More messages** opens Messenger (Facebook posts) or Instagram Direct (Instagram posts).
  WhatsApp needs a WhatsApp number linked to the Page; it is not in this release.
- **More website visits** needs a link on the post (set when a text post was published with a
  link); without one the dialog says so.
- **Location default**: no city is stored on a customer, so the default is Kerala for Indian
  clients and the customer's country otherwise. Staff can add or remove places.
- **Tab and chip**: the Ads tab is for the same people as Credentials and Meta; editors use the
  post's Boost section.
- Disconnecting Meta is refused while a boost is Active or Paused.

### Owner setup for ads

1. In the Meta app, **App Review** for `ads_management` and `ads_read` (Advanced Access),
   alongside the Phase 1 permissions. Use the screencast notes below.
2. Each client must let TBO run ads on their **ad account**: either add **TBO's Business as a
   partner** on the ad account (Business Settings → Accounts → Ad accounts → Add partner), or
   the person who connects Meta must have an **advertiser** (or admin) role on that ad account.
   Without it, Meta answers with a permission error and the hub says to ask for partner access.
3. The client's ad account needs a **payment method** (Business Settings → Payments). The hub
   never handles payment; without it a boost stays unable to run and the page says so.
4. In the hub, **Settings → Meta → Paid ads → Enable ads**. Do this after the review passes (or
   test with app testers).
5. Per client: project **Meta** tab, **Reconnect Meta to allow ads**, pick the ad account, and
   set the **monthly limit** (default 10,000).

### Screencast notes for ads_management and ads_read

Narrated, English, on the live HTTPS hub with a test ad account that has a payment method:

1. Meta tab: **Reconnect Meta to allow ads**, Facebook's dialog listing `ads_management` and
   `ads_read`, then the ad account list and picking one (shows `ads_read`: listing accounts).
2. Content calendar: a Published post, **Boost this post**, the goal, budget, dates, audience and
   the summary. Press **Start boost** and show the campaign in Meta Ads Manager created from the
   existing post (`ads_management`: creating and editing campaigns, ad sets and ads).
3. The project **Ads** tab with spend and results (`ads_read`: insights), then **Pause** and
   **Stop boost**.
4. Say plainly that the hub only boosts posts staff chose, never spends beyond a monthly cap, and
   that the client pays Meta directly.

## Tests

`helpdesk/tests/test_meta_publishing.py`, with Graph mocked by `FakeGraph` in
`helpdesk/test_utils.py` (no real Meta call): state signing, tampering and expiry; the
callback storing the encrypted token and never returning it; picking a Page; permissions
(member and Sales Employee refused); Instagram image, carousel and video (polling); Facebook
photo, several photos and text; the quota; not-approved refused; scheduling and cancelling;
the scheduler publishing a due row once; retry with backoff then failure with a
notification; an expired token marking the connection; stuck rows; signed media URLs.

`helpdesk/tests/test_meta_ads.py` (same `FakeGraph`): scopes with and without ads; keeping or
dropping the user token; picking the ad account; "Reconnect Meta to allow ads"; a boost built
PAUSED and switched on last; Instagram and lifetime-budget variants; the monthly cap (refused
before anything is sent, counting earlier boosts, re-checked at approval); editor request and
head approval and rejection; who may spend, view and change the limit (Sales Employee sees
nothing); insights sync and the hourly job; pause, resume and stop; Meta refusals (payment,
access, expired token, a disapproved ad) surfaced in plain words.

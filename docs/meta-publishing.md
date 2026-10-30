# Publish to Meta (Facebook and Instagram)

TBO is also a digital-marketing agency. From the content calendar, a client-approved post
can be pushed straight to the client's Facebook Page and Instagram account, with the
official Meta Graph API. This is **Phase 1** (organic posts). Paid Boost and Ads are
[Phase 2](#phase-2-paid-ads).

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
`instagram_content_publish`, `business_management`.

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
- Reading insights or comments back.
- Deleting a post on Meta from the hub.

## Phase 2: paid ads

The connection is built so ads need no rework:

- `SCOPES` in `connect.py` is the one list. Phase 2 adds `ads_management` and `ads_read`
  (and App Review for them); clients who already connected see Connect again, which repeats
  the same flow with the larger scope list. `HD Meta Connection.granted_scopes` records what
  each client allowed.
- Page tokens stay for organic posting. Ads act through a **user** access token of a person
  with access to the ad account; Phase 2 will keep that token the same encrypted way, in a
  field next to the Page's, and add the ad account id (`act_...`) to the connection.
- A Boost is a Marketing API campaign (campaign, ad set, ad with the published post as its
  creative `object_story_id`, which is why `meta_post_id` is stored per target). It would
  be a button on a Published row, budget and audience asked in a dialog, with the same
  permission rule, the same `GraphClient` and the same error handling.
- Billing stays on the client's ad account; the hub never touches payment.

## Tests

`helpdesk/tests/test_meta_publishing.py`, with Graph mocked by `FakeGraph` in
`helpdesk/test_utils.py` (no real Meta call): state signing, tampering and expiry; the
callback storing the encrypted token and never returning it; picking a Page; permissions
(member and Sales Employee refused); Instagram image, carousel and video (polling); Facebook
photo, several photos and text; the quota; not-approved refused; scheduling and cancelling;
the scheduler publishing a due row once; retry with backoff then failure with a
notification; an expired token marking the connection; stuck rows; signed media URLs.

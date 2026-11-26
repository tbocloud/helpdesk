# Reach report (Meta insights)

How far each client's Facebook Page and Instagram account reached: reach, views,
engagements, followers, and which posts did best. It is built on the Meta connection from
[meta-publishing.md](meta-publishing.md): the same app, the same Page token, one connection
per project. Not to be confused with the **Delivery report**, which measures whether posts
went out on time.

Code: `helpdesk/integrations/meta/insights.py` (the sync), `helpdesk/api/meta_insights.py`
(the report, Sync now, the PDF), `helpdesk/templates/reach_report_pdf.html`,
`desk/src/pages/content/ContentReach.vue` (route `ContentReach`, `/content/reach`).
Tests: `helpdesk/tests/test_meta_insights.py`.

## Switching it on

1. Meta App Review approves `read_insights` and `instagram_manage_insights`, with a screen
   recording of the Reach report (the hub showing a Page's and an account's numbers).
2. A System Manager turns on **Settings → Meta → Enable reach reports**
   (`HD Meta Settings.insights_enabled`). Until then nobody is asked for the permissions:
   asking for unapproved ones would only work for the app's testers.
3. Each client connects Meta again (project → Meta → **Connect again**) and allows them.
   Clients connected before the switch have `insights_allowed` off and the report says so.

The insights permissions are asked for like the ads ones (`connect.INSIGHTS_SCOPES`,
`connect.scopes()`) but are **not required**: a client who declines them still connects
and publishes; `HD Meta Connection.insights_allowed` stays off.

## Data

| Doctype | What |
| --- | --- |
| **HD Meta Daily Insight** | One row per project, platform and day, named `<project>-<platform>-<day>` so a re-sync updates it. `reach`, `views`, `engagements`, `engaged_accounts` (Instagram), `follows`, `unfollows`, `followers` |
| **HD Meta Post Insight** | One row per post, named `<platform>-<Meta id>`. `kind` (Image, Carousel, Video, Reel, Story, Text, Other), `posted_on`, `caption`, `permalink`, `thumbnail_url`, `reach`, `views`, `reactions`, `comments`, `shares`, `saves` (Instagram), `clicks` (Facebook), `interactions`, `content_post` (the calendar post the hub published it from), `insights_note`, `last_synced` |
| **HD Meta Connection** (new fields) | `insights_allowed`, `insights_synced_on`, `insights_error` |

Both doctypes are System Manager only and read-only in the desk; the API reads them after
its own check. Rows stay when Meta is disconnected and show again once the project
reconnects.

`followers` is only known for "now" (Meta gives no history), so each sync writes it on the
last day it read; days filled in later have 0 and the report ignores them.

## The sync

| When | What |
| --- | --- |
| Nightly (`daily`, `insights.sync_all`) | The last 3 days (Meta can be 48 hours late) and the numbers of posts from the last 30 days, for every Connected project with `insights_allowed` |
| Hourly (`insights.sync_stories`) | Instagram Stories still up: their numbers are gone 24 hours after posting |
| Picking the Page, **Sync now** | The last 90 days, in the `long` queue (`insights.queue_sync`, deduplicated per project) |

Nothing runs while the switch is off. An expired token marks the connection Expired, as
publishing does. Errors go to `insights_error`, which the report shows.

### What is asked of Meta

The names are maps at the top of `insights.py`, the one place to change when Meta renames
a metric.

| Level | Call | Metrics |
| --- | --- | --- |
| Page, per day | `GET <page>/insights?period=day&since&until` (90 days a call) | `page_total_media_view_unique` (reach), `page_media_view` (views), `page_post_engagements`, `page_daily_follows_unique`, `page_daily_unfollows_unique` |
| Instagram, per day | `GET <ig>/insights?metric_type=total_value&period=day`, one call per day | `reach`, `views`, `accounts_engaged`, `total_interactions`; `follows_and_unfollows` by `follow_type` asked alone (a breakdown fails a call with other metrics; none under 100 followers) |
| Followers | `GET <page>?fields=followers_count`, `GET <ig>?fields=followers_count` | total now |
| Facebook posts | `GET <page>/published_posts` (with `shares`, `comments.summary(true)`), then `GET <post>/insights` | `post_total_media_view_unique`, `post_media_view`, `post_clicks`, `post_reactions_by_type_total` (added up) |
| Instagram posts | `GET <ig>/media`, `GET <ig>/stories`, then `GET <media>/insights` | `reach`, `views`, `likes`, `comments`, `shares`, `saved`, `total_interactions`; Stories only `reach`, `views`, `shares`, `total_interactions` |

Decisions:

- **Retired metrics don't stop the sync.** Meta retired `impressions` (April 2025 on
  Instagram, November 2025 on Pages) and more Page metrics in June 2026. When a request is
  refused with "(#100) … valid insights metric", each metric is asked alone and the refused
  ones are skipped and named in `insights_error` ("Meta no longer gives these numbers: …").
  Code 100 without "metric" in the message (an object without insights) is a real error.
- **A Story with fewer than 5 viewers** (Meta's code 10) is kept with a note instead of
  numbers.
- **Facebook videos** are kept by the publisher under their video id; Meta lists them as
  `<page>_<video id>`, so `content_post` is matched on either.
- **Reach is added up day by day.** Meta has no unique reach for an arbitrary period; the
  page and the PDF say a person reached on two days counts twice.
- **Thumbnails are Meta's links**, which expire; the page shows a kind icon when one breaks.

## Who sees it

- **The report** follows the content calendar's visibility (`hd_content_post.permission_query`):
  only the content team; its leads (project managers, DM Coordinators, the Digital Marketing
  Head, System Managers) see every client, the rest the clients whose projects they are on.
- **Sync now** follows `can_handle_credentials(project)`, like connecting Meta.
- The PDF uses the report's check.

## The page

Content Calendar → **Reach report** (next to Delivery report; also under the Content nav
item). Filters: **Client** (each connection, "Customer · Page"), **From**, **To** (this month
by default, at most a year). The project's Meta tab links here with `?project=`.

- **Tiles**: Reach, Views, Engagements (with the engagement rate of the period's posts:
  interactions ÷ reach), Followers (with net new followers). Each adds Facebook and
  Instagram, shows the split underneath, and the change against the period just before.
- **Day by day**: a line per platform (brand teal and a neutral, named in the legend) for
  Reach, Views or Engagements (`TabButtons`), days up to yesterday.
- **Posts by reach**: the top 50 with thumbnail, caption, platform, kind, date, reach,
  interactions, a link to the calendar post and to the live post.
- **What works best**: average reach per post by kind.
- States: reports switched off, no client connected, client hasn't allowed insights (with
  a link to the Meta tab), first sync running, sync error, nothing posted.
- **Download PDF** (for the client): the summary table, daily reach as bars (the PDF can't
  run the chart), by kind and the top 15 posts. It uses `helpdesk.utils.send_report_pdf`,
  shared with the delivery report and the division reports (a print-ready page where
  wkhtmltopdf isn't installed).

## Not done

- Audience demographics (age, gender, city), and Facebook Page demographics.
- Paid reach: boosts keep their own numbers on `HD Meta Boost` (meta-publishing.md, Phase 2).
- A client-facing view in the portal; the PDF is what clients get.

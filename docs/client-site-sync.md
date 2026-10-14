# Client-site sync health

The hub calls each customer's ERP over MCP (`HDS Support Connection`). The calls come from
these scheduled jobs:

| Job | When | What |
| --- | --- | --- |
| `ticket_puller.pull_client_tickets` | every minute | pulls Pending support tickets |
| `ticket_puller.push_ticket_statuses` | every 5 minutes | mirrors ticket statuses back |
| `ticket_puller.sync_conversations` | every 5 minutes | syncs comments, files and close requests |
| `content_sync.sync_content_approvals` | every 5 minutes | handles content approvals |
| `tasks.health_check_connections` | daily | lists the MCP tools |

A site that is down for maintenance or returns 503 used to be called every minute, and each
failure wrote an Error Log. On 4–5 Oct 2026 that produced about 3,700 rows for two sites.
This page describes how the hub now treats a site that keeps failing.

## Backoff

The state is kept on the connection, in `consecutive_failures`, `last_error`,
`unreachable_since` and `next_attempt_at` (read only). It is changed by the
`HDSSupportConnection` methods `record_failure` and `record_success`.

1. **First and second failure in a row.** The status becomes **Error**, with the reason in
   `last_error`. The next run tries again; a short blip shouldn't hold up tickets.
2. **From the third failure.** The status becomes **Unreachable** and the hub waits before
   the next call: 1, then 5, then 15, then 60 minutes (`BACKOFF_MINUTES`). It stays at 60.
   `next_attempt_at` holds the time of the next call.
3. **Success.** The status goes back to **Connected**, and the count, the wait and
   `unreachable_since` are cleared.

The jobs follow the backoff like this:

- **The per-minute pull and the daily health check** call only the connections that are due
  (`ticket_puller.due_connections`), so they are the probe that finds a recovery.
- **The 5-minute jobs** skip Unreachable connections (`ticket_puller.unreachable_connections`).
  When they can't open an MCP session (`ticket_puller._connect`), it counts as a failure
  instead of an Error Log.
- **A site's own "ticket raised" ping** (`support_hub.ticket_raised`) pulls straight away,
  even when the connection is Unreachable. The ping shows the site is up.
- **Registering again, or setting the status to Connected by hand,** clears the backoff
  (`reset_backoff_when_connected`).

Failures inside a run that already has a session, such as one ticket failing to import, are
still logged per record, as before.

## One message per outage

When a connection first becomes Unreachable, the hub sends:

- **one Error Log**, titled `Customer site unreachable: <customer>`, with the site, the
  number of failures, the next call and the last error;
- **one notification**: `notify_users(..., escalate=True)` to the System Managers, which
  posts to the team's Teams or Slack channel when it is set up.

When the site answers again, the hub sends one "reachable again" notification. It says how
long the outage lasted. There is no Error Log for a recovery, because it isn't an error.
Nothing is sent for the failed attempts in between.

## Where it shows

- **Connection status.** The connection status has a fifth option, **Unreachable**.
- **Home, Systems card (admins).** The status badge shows Unreachable in red. The row shows
  the last error and the time of the next call.
- **Customer page.** The banner under the header shows "ERP unreachable: <error> · next try
  at <time>". The shared helper is `connectionProblem` in `desk/src/composables/customer.ts`.
- **Customer health.** An Unreachable connection is at risk, like one in Error
  ([customer-health.md](customer-health.md)).

## The error digest and the backlog

- **The error digest** (`error_alerts.post_error_digest`, every 10 minutes) groups titles
  that differ only by numbers (`group_similar`). For example, "Status push failed for 101",
  "…102" and "…103" become one line: "3 × Status push failed for 101 (and 2 similar)".
- **Mark old sync errors as seen** (Settings → Chat & Teams → Error alerts, System Managers
  only) marks the sync errors older than a day as seen. These are the titles in
  `error_alerts.SYNC_ERROR_TITLES`. The action runs only when someone clicks it. It is
  never scheduled and never deletes anything. The Error Log's own 30-day cleanup still
  applies.

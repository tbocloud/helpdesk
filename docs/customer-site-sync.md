# Customer site sync

How TBO Support keeps a customer's own ticket (the `Support Ticket` on their ERPNext, made by `helpdesk_client`) in step with the hub's HD Ticket. The code is `helpdesk/ticket_puller.py` and `helpdesk/approval.py`.

## Pulling tickets

Every minute (`pull_client_tickets`), and at once when a customer site pings `ticket_raised`, the hub reads the site's Pending tickets over MCP, creates the HD Ticket with its files, and writes the hub number and `Open` back onto the customer's ticket.

## Writing back

- A write the customer site refuses (writes switched off there, a label its status field does not accept) is an error, never a success. `_push_back` raises, the ticket is retried next run, and the failure is logged **once an hour** per ticket, not every run.
- The status push (`push_ticket_statuses`, every five minutes) sends a ticket only when its payload (status, priority, hub number) changed since the last successful push. The last payload's hash is kept in the hidden field `custom_client_push_hash` on HD Ticket. A quiet hub makes no writes on customer sites.
- Status labels are mapped to the customer app's own list (`Pending, Open, Replied, Paused, Resolved, Closed`): a hub status outside that list is mapped by its category (Open → Open, Paused → Paused, Resolved → Resolved), so "Waiting on Task" reaches the customer as `Paused`. A status with no mapping is left out of the update; the hub number and priority still go through.
- Agent replies are marked as sent to the customer only when the customer site accepted them. The sync state (`custom_sync_state`) is saved after each step, because `MCPClient` commits after every audited call: a failure later in the same ticket must not re-import comments the hub already has.
- A customer's close request closes the HD Ticket through the controller, so the status category, the SLA and the usual hooks follow.

## Approving AI writes

An `HDS Support Action Request` is decided (approved or rejected) once and executed once. The decision and the execution take a row lock, and the request is marked `Executing` before its first remote write, so a second click or a second worker cannot run the same customer writes again.

## Triage status

`custom_triage_status` accepts every value triage writes: `Pending`, `In Progress`, `Completed`, `Skipped`, `Failed`.

## Fix brief

The brief's "Done when" list names the ticket's task (`Closes TASK-…`) when one exists, because GitHub sync links a pull request to its task by that reference and the task-reference check refuses a pull request without one. Without a task it asks for one to be created first.

## Tasks from tickets

`create_task_from_ticket(..., pause_ticket=True)` keeps pausing the ticket ("Waiting on Task") by default. With `pause_ticket=False` the ticket stays as it is and its SLA keeps running; Copilot runs use this because they report their own progress on the ticket.

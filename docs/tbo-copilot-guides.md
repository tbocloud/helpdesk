# TBO Copilot: a guide for each role

Who does what, what Copilot sends you, and what you press. The full reference is [tbo-copilot.md](tbo-copilot.md). Who holds each role is set in **HDS Copilot Settings → People** (every customer) and **HD Customer → Copilot People** (one customer); see "People" in the reference.

## The customer (on their ERP site)

- **Support button:** opens the chat with TBO Copilot. Write what happened in your own words; Copilot answers from TBO's guides, or asks a few questions and raises a ticket. **Talk to a person** hands you to TBO's team at once.
- **After the ticket is raised,** the same chat is the ticket's channel: the team answers there, and what you write reaches them, even while the AI is switched off. If a message cannot be sent, it stays in the box and the chat says so; press Send again.
- **Stages** show where your ticket stands: Working on it, Waiting for you, With our team, Fix scheduled, Resolved.
- **Resolved:** press **It's fixed** to close the ticket, or **Still broken** with what is still wrong. The question comes again after every fix.
- **The ticket form** (sites without the chat): a comment you add is your reply; the team hears it.
- Nothing on your site is changed without a TBO senior's approval, and every change is logged on your site.

## An agent (TBO Support)

- **The ticket's Copilot chat** (on the ticket page) shows what Copilot found, its draft reply and its buttons. Copilot never sends anything to the customer by itself: you read the draft and send it.
- **Buttons that ask for a reason** (Reject…, Undo…) open a box. A button that is refused says why in a message at the top.
- **The paperclip** attaches files to the chat (the panel and the ticket chat).
- **"What is waiting for me?"** in the Copilot panel or Teams lists your fix approvals, release and action approvals, and tickets waiting for you to choose who takes them. The same list comes at 09:00 each working day.
- **A task's "Open in TBO Copilot"** opens the task in the desktop app with its project's folders. Without the app, the notice offers **Install**.

## A project coordinator

- **Every new ticket** of your customers comes to you as a card (Teams, else the TBO Support panel), with who has it and who Copilot goes to.
- **Assign to:** pick a person (the customer's own people come first) and press **Assign**; **Keep** leaves it with whoever has it. The first choice stands; **Change** on the decided card picks again. Assigning the ticket by hand on the ticket page also ends the wait.
- **When no developer can take a ticket** (none set, or none working today), you are asked to choose. The card comes again at 06:45 on working days.
- **Every step of your customers' tickets** comes to you too: Copilot's diagnosis, a fix ready, approved or rejected, the deploy, resolved or reopened, failures, and each reply from the customer. **Mute this ticket** on a message stops one ticket.
- **Talk to a person:** when a customer asks for a person, the coordinator working today joins the ticket and handles the customer.
- **You do not approve fixes or press Deploy**: that stays with the developers, fix approvers, Seniors and Leaders, even on a ticket you gave to yourself.
- You also write in the ticket chats of your customers, and hear risk alerts (with the settings' tick).

## A developer or fix approver

- **Fix approvals** reach you as a card with the change, its risk, its checks and **Approve** / **Reject…**. You never approve a fix you wrote; a fix in a sensitive area goes to a Senior.
- **Main, then fallbacks:** while you are on leave or Unavailable, the next person in Copilot People gets the work; a waiting approval moves to them the next working morning.
- **Deploy:** after the merge, press **Deploy** (Tonight). Approving an automatic deploy is enough: it needs no second permission.
- **Going live from a task** (desktop app): ask for your task's release to go live; the approver's card carries your request and your note.

## A Senior or a Leader

- **Seniors** decide sensitive fixes, data and settings corrections, releases that need a senior, **Deploy now**, and letting a release through without green CI or a staging check (with a reason).
- **Leaders** are the last resort: escalations, approvals nobody else could take, "Copilot needs a person", failed deploys, the AI budget, the weekly pilot email. With no Leader set, the Agent Managers get these, and the settings page warns.
- **Leaders also see everything** in TBO Support's notifications (the bell), never in Teams: each new ticket of every customer, and every step of every ticket (the same steps the coordinators get). Teams stays for what you must act on.
- **Deploy now** on a fix scheduled for tonight moves the same deploy to now.
- **Leaders** approve risky infrastructure actions when no Infrastructure Senior is working (a deploy, restore or new site; later: rollback, reboot, MariaDB), and take an alert when Copilot's action did not fix it.

## An admin (System Manager)

- **HDS Copilot Settings → People:** one row per role and person: Role, Person, Level (Main, Fallback 1–3), Active, Until (a temporary cover). A customer's own rows (Developer, Fix Approver, Project Coordinator) are on the customer, in **Copilot People**; an empty Developer follows the customer's Ticket Owner and Backup.
- **Who Copilot Goes To Today** (same page) shows every role and customer, who gets the work now and why, and warns about empty roles, no Leader, people who are not active agents, disabled accounts and ended covers.
- **Hand over someone's places** (button on the page): someone leaves or changes job. It counts first, then moves every row and their waiting fix approvals.
- **After a deploy:** `helpdesk.api.monitor.deploy_check` (System Manager) shows each app's version and commit and whether the last migrate finished.

## DevOps (Infrastructure people)

- **Press, AWS and repair actions** come to the Infrastructure people as cards; a risky one goes to Infrastructure Senior (else a Leader). Nobody approves their own request.
- **Copilot on alerts (Phase 25):** when the watcher opens an alert, the TBO Copilot bot tells you ("Alert: …"), Copilot looks into it and posts what it found. When one of its listed actions (back up, restart a bench, migrate or update a site) would help on a place it may change, you get an **Approve / Reject** card; nothing runs before that. Otherwise its card says what a person should do. Reply in Teams to ask it why. After an approved action, the watcher's next checks decide: healthy is "Fixed by Copilot"; still failing after 30 minutes goes to a Leader.
- **The watcher's alert tickets** go to the internal customer's ticket owner (else the backup, else the internal project's team); its **follow-up tasks** (a disk filling, a certificate expiring) go to the Infrastructure person working today, else a Leader, with a comment saying why. "pause auto-repair: <why>" and "resume auto-repair" in Teams work for you and the Leaders.
- **HDS Hub Settings → Monitoring** shows **Watcher last seen**; "Quiet" means no heartbeat for the quiet time.
- **Deploy notices:** one per Press deploy (started, live, failed), naming every release in the night's train.
- **The watcher** reads the hub's `self_check`, which now includes the deploy state: a migrate that stopped half-way shows as patches still pending.

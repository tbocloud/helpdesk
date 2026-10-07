# AI task descriptions

Every task should say what it is for, how to do it and when it is done. The AI drafts that
description in two ways:

- **Write with AI** in the New task and Edit task dialogs fills the Description box with a
  draft the person can edit before saving.
- A task **created with no description**, by any path, gets one written in the background.

Code: `helpdesk/task_descriptions.py`. Tests: `helpdesk/tests/test_ai_task_descriptions.py`.

## Write with AI (dialogs)

- `desk/src/pages/tasky/components/TaskDescriptionField.vue` replaces the Description
  textarea in `NewTaskDialog.vue` and `EditTaskDialog.vue` (both the lead/manager form and the
  assignee's description-only form). The button sits next to the Description label.
- It sends the current form (task name, category, phase, priority, estimated hours, project,
  assignee; plus the task when editing) to `draft_task_description` and puts the answer in the
  box. Nothing is saved until the person saves the dialog.
- If the box already has text, it asks first: **Replace** or **Add below** (or Cancel).
- Disabled until a task name is typed, and while a draft is loading. Errors show under the
  box. When AI isn't set up (`get_ai_status` says unavailable) the button is disabled and the
  reason is shown under the box.
- The assignee's form sends the saved task details (they can only change the description).

## Background descriptions for new tasks

- `Task.after_insert` → `queue_ai_description` → `should_describe`: the description is empty
  (after stripping HTML), the status isn't Template, Completed or Cancelled, the setting is on
  and AI is set up. This covers every path that inserts a Task: the dialogs, template
  checklists (`generate_checklist`), content-post tasks, ticket → task, the API and imports.
- `queue_description` collects the task names of the transaction in `frappe.flags` and
  registers one `frappe.db.after_commit` callback (and an `after_rollback` one that drops the
  list). After commit, `enqueue_pending` sends them out in batches of 10
  (`BATCH_SIZE`) to the `long` queue as `describe_tasks` jobs (`job_id`
  `ai-task-descriptions-<first task>`, deduplicated). A 40-task template is 4 jobs, not 40.
- `describe_tasks` runs as the automation user (`helpdesk.automation.automation_user`) and
  pauses 2 seconds between AI calls (`PAUSE_SECONDS`) so a large template doesn't hit the
  provider in a burst. One failing task is logged ("AI task description failed for …") and
  the rest go on.
- **Never overwrites a person's text.** The job re-reads the task and skips it if it has a
  description by then; the write itself is a conditional `UPDATE … WHERE description` is
  still what the job read, so text typed while the AI was writing is kept. The write doesn't
  change `modified`, so nobody's open dialog gets a "document has been modified" error.

## Setting

**HD Work Settings → "Write descriptions for new tasks with AI"** (`ai_task_descriptions`,
Check, default on). Patch `helpdesk.patches.v16_0_2.enable_ai_task_descriptions` turns it on
for existing sites (a Single's default only applies to new sites).

It is edited in the helpdesk app: **Settings → App Settings → Tasks**
(`desk/src/components/Settings/Tasks/TaskSettings.vue`, System Managers, since HD Work
Settings is writable by them only), next to "AI sets the time for new tasks" and the longest
estimate. The setting only controls the background job; **Write with AI** works whenever AI is
set up.

"AI is set up" means HDS Hub Settings has an AI key (`helpdesk.ai_suggestion.is_ai_configured`).
Without one: no background job is queued, the dialog button is disabled with the reason, and
the endpoint refuses with "AI isn't set up…".

## AI call

Reuses the hub's AI plumbing: `helpdesk.ai_engine.call_haiku` (the triage model and provider
from HDS Hub Settings, its retry with a larger token budget, JSON parsing and
**HDS AI Usage Log** usage logging). No new provider or key.

### Prompt outline (`SYSTEM_PROMPT`)

- Role: writes task descriptions for TBO (ERPNext implementation, mobile apps and websites,
  digital marketing and content).
- Shape, plain text: one or two sentences on the goal; `Steps` with 3–6 "- " bullets starting
  with a verb; `Done when` with 2–4 checks someone else can verify.
- Tone by category: ERP / development / DevOps → configuration or code, testing with sample
  data, a short note or document; creative (design, video, motion graphics, social media,
  content writing, digital marketing) → deliverables, sizes/formats/channels when they follow
  from the task, brand guidelines, internal review before the customer sees it; support and
  coordination → who to talk to, what to agree, where to record it.
- Rules: no Markdown, under 150 words, use only what is given and never invent customer
  facts (write a step that asks instead), sibling tasks are context only, no personal data,
  credentials or links.
- Answer: JSON `{"description": "..."}`. A plain-text answer is accepted too.

### What the AI is given (`task_context`)

- Task: name, category, phase, priority, estimated hours, and the assignee's **project role**
  (e.g. Graphic Designer), never their name or email.
- Project: name, customer, department, project type, and the project notes (HTML stripped,
  first 1200 characters).
- Up to 5 other task names in the same phase of the project (not Template or Cancelled).

`clean_description` strips HTML and Markdown markers (`#`, `**`, `*`/`•` bullets become
"- "), collapses blank lines and caps the text at 1500 characters.

## Storage and the "AI drafted" mark

- Task.description is a Text Editor field, but the task dialogs edit it as a plain textarea,
  so the AI's text is stored as plain text with line breaks. The task panel in My Work renders
  descriptions with `whitespace-pre-line` so those line breaks show.
- **`Task.custom_ai_description`** (Check, read-only, no copy; custom field in
  `helpdesk/setup/install.py`) means "written by the AI and not edited since". It is set by the
  background job, and by `add_task` / `update_task` when the dialog sends
  `ai_description: true` (the box still holds the unedited AI draft, including "Add below"
  where the draft follows the person's text).
- `Task.validate` → `unmark_ai_description_when_edited` clears it when the description changes
  on a save that isn't flagged as AI (`doc.flags.ai_description`), from any path including the
  desk form.
- Shown as a small gray **AI drafted** chip (`AiDraftedChip.vue`) next to the Description label
  in the dialogs and in the My Work task panel. `_format_task` returns it as `ai_description`.

## Permissions

| Endpoint | Rule |
| --- | --- |
| `helpdesk.task_descriptions.draft_task_description` (POST) | New task: may read the project and `can_add_tasks` (admins, the project's managers and lead, members, people with a task in it). Editing (`task` given): read permission on the task and the same rule as saving its description (`_check_can_edit`: lead, manager or the assignee). Also refuses when AI isn't set up, and after 30 drafts per person in 10 minutes. |
| `helpdesk.task_descriptions.get_ai_status` (GET) | Any logged-in user; returns only whether AI is set up and why not. |

The background job writes with a direct conditional update (no permission check) as the
automation user; it only ever fills an empty description.

# Project files

People on a project share files there: the owner's master prompt as a `.md` file, briefs and
contracts as PDFs, designs, spreadsheets. Everyone on the project can see and open every file.
A file can be marked as **for** one or more people on the project; they are notified, and
the label is a pointer, not a restriction.

## Where it is in the app

- **Project page → Files tab** (`/helpdesk/projects/<project>/files`, route `TaskyFiles`,
  `desk/src/pages/tasky/ProjectFiles.vue`). The tab in `ProjectNav.vue` shows the file count.
  The project cards on the Projects page show a paperclip button with the count when a
  project has files; it opens the Files tab.
- **Add files** opens `UploadProjectFilesDialog.vue`: pick several files at once or drop
  them in the dialog, or drop files anywhere on the Files page (which opens the dialog with
  them). Files over the site's limit are flagged before upload. Each file shows its own
  state (uploading, added, or the server's error); files go one at a time so one failure
  doesn't stop the rest, and the dialog stays open while something failed. The **For**
  picker (`FileForPicker.vue`, checkboxes of the project team) applies to every file in that
  upload.
- **List**: icon by type, file name, size, who added it, when, and "For:" chips. Files for
  the current user get a "For you" badge and a tinted row. **For me** narrows the list to
  them. Row actions: View (Markdown, text, PDF, images), Download, Change who it's for, and
  Delete (with a confirmation).
- **Viewer** (`ProjectFileViewer.vue`):
  - `.md` / `.markdown`: rendered Markdown. `marked` turns it into HTML and `sanitize-html`
    keeps only harmless markup (no scripts, styles, images or event handlers; links open in a
    new tab with `noopener`), because files are user content. **Copy text** copies the raw
    file, which is what you paste a master prompt from.
  - `.txt`: shown as plain text, with Copy text.
  - PDF: the browser's PDF viewer in the dialog, plus **Open in new tab**.
  - Images: a preview.
  - Everything else: the file name and the Download action download it.
- Notifications open the Files tab of the project.

## Who can do what

| Action | Who |
| --- | --- |
| List, view, download | Anyone who can read the project: admins (System Manager, Agent Manager), the project's managers (creator, or "Project Manager" role on the project), the lead, members, and people with a task in it |
| Upload | The same people (`can_add_tasks`): the owner wants to share prompts, and members contributing files (designs, notes) is useful |
| Change who a file is for | The person who added it, the project lead, the project's managers, admins |
| Delete | The person who added it, the project lead, the project's managers, admins |

"For" can only name people on the project team: its members plus its lead
(`get_project_team` in `helpdesk/tasky/permissions.py`). Anyone else is refused.

### How opening a private file is authorised

Files are saved private, so their URL is `/private/files/<name>`. Frappe serves those only
after `File.is_downloadable()`, which runs Frappe's `File.has_permission`: for a file attached
to a document it checks **read** permission on that document. Here that is the Project, whose
read access comes from the Agent role's read permission narrowed by
`helpdesk.tasky.permissions.project_has_permission` (members, lead, managers, people with a
task in it, admins). So a project member who is not a System Manager can open the file, and an
outsider gets a 403, without a separate download endpoint. `test_project_files.py` checks both
cases through `frappe.has_permission("File", ...)` and `is_downloadable()`.

Write and delete on the File through Frappe's own API need **write** on the Project, which only
managers have; members delete their own files through `delete_project_file`, which checks the
rules above and then deletes with `ignore_permissions`.

## Storage

- Each upload is a Frappe **File** with `attached_to_doctype = "Project"`,
  `attached_to_name = <project>` and `is_private = 1`. It is created by inserting the File
  doc like any attachment, so the site's **max file size** (System Settings, else
  `max_file_size` in site config, else 25 MB) is enforced server side by `File.save_file`, and
  the browser checks the same limit (returned by `list_project_files`) before uploading.
- **S3 (HD File Storage Settings)**: the File `after_insert` hook
  (`helpdesk.storage.s3.after_insert`) moves new attachments to the bucket when their
  document type is listed in the settings, the same path content-post attachments take. To
  keep project files in the bucket, add **Project** to the settings' document types. Files in
  the bucket open through `helpdesk.storage.s3.download`, which runs the same
  `is_downloadable()` check; the Markdown viewer reads the content server side
  (`File.get_content()`, which the `HelpdeskFile` override reads back from the bucket).
- The upload does not go through Frappe's `upload_file`, because that requires write on the
  Project and members only have read. `upload_project_file` takes the same multipart request
  (frappe-ui's `FileUploadHandler` with `upload_endpoint`) and checks project access itself.

## Data model

- **HD Project File** (`helpdesk/helpdesk/doctype/hd_project_file`): one per uploaded file.
  `project` (Link Project), `file` (Link File, unique), `file_name` (fetched from the File),
  `for_users` (Table → **HD Project File User**: `user` Link User, `full_name` fetched).
  Only System Manager has role access; everything else goes through the API.
  - `validate`: the File must be attached to that project; `for_users` must be on the
    project team; duplicates are dropped.
  - `on_update` (also runs on insert): people added to `for_users` since the last save are
    notified, except the person making the change.
- Why a separate doctype and not a field on File: the "For" list needs a child table (a JSON
  list in a custom field was ruled out), and File is a core doctype; a small wrapper keeps the
  File untouched and lets the list be queried with a join.
- Files attached to a project without an HD Project File (e.g. uploaded from `/app`) still
  show in the list with an empty "For"; changing who they are for creates the record.
- Deleting a File removes its HD Project File (`HelpdeskFile.on_trash` in
  `helpdesk/overrides/file.py`). Deleting a project deletes its attachments, and with them
  their records; `HD Project File` is in `ignore_links_on_delete` so its link to the project
  doesn't block that.

## Notifications

`helpdesk.work_reminders.notify_users` (bell, plus email or Teams per HD Notification), with
the message "<who> shared <file name> with you in <project name>" and a link to
`/projects/<project>/files`. Only people who weren't already on the file's "For" list are
notified, and `notify_users` also skips anyone who already has that exact notification for the
file, so removing and re-adding someone doesn't notify them again.

## API (`helpdesk/api/project_files.py`)

Every call checks read access on the project first, and every call that names a file refuses
a File that isn't attached to that project (`PermissionError`).

- `list_project_files(project, for_me=False)` (GET): `{files, total, team, can_upload,
  max_file_size}`. Each file: `name`, `project_file`, `file_name`, `file_url`, `file_size`,
  `uploaded_by`, `uploaded_by_name`, `creation`, `for_users` (`[{user, full_name}]`),
  `is_for_me`, `can_delete`, `can_edit_for`.
- `upload_project_file(project, for_users=None)` (POST, multipart field `file`): saves one
  file. `for_users` is a JSON list of users. Uses `add_project_file(project, file_name,
  content, for_users)`, which tests call directly.
- `set_project_file_for(project, file, for_users)` (POST): replaces the "For" list.
- `delete_project_file(project, file)` (POST).
- `get_project_file_text(project, file)` (GET): content of a `.md`, `.markdown` or `.txt`
  file up to 2 MB, for the viewer.
- `file_counts(projects)` (not whitelisted): used by `get_projects` and `get_project_detail`
  in `helpdesk/tasky/api.py` for the `file_count` on cards and the tab.

## Tests

`helpdesk/tests/test_project_files.py` (helpers `make_project_file`, `run_as_user`,
`hold_commits`, `get_reminder_messages` in `helpdesk/test_utils.py`): members list and open a
private file, outsiders can't list or open it, members upload and outsiders can't, the uploader
and the manager delete while another member can't, a file from another project is refused,
two assignees are notified once each, a non-member can't be an assignee, editing the list
notifies only the new people, only the uploader or managers change it, and "For me" lists only
the user's files while everyone still sees all of them.

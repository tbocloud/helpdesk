# Project files

People on a project share files there: the owner's master prompt as a `.md` file, briefs and
contracts as PDFs, designs, spreadsheets. Everyone on the project can see and open every file.
Files can sit in **folders**, nested up to five levels. A file or a folder can be marked as
**for** one or more people on the project; they are notified (in Teams when it is set up), and
the label is a pointer, not a restriction.

## Where it is in the app

- **Project page → Files tab** (`/helpdesk/projects/<project>/files`, route `TaskyFiles`,
  `desk/src/pages/tasky/ProjectFiles.vue`). The tab in `ProjectNav.vue` shows the file count.
  The project cards on the Projects page show a paperclip button with the count when a
  project has files; it opens the Files tab.
- **Folders**: the page shows the folders of the open folder (or of the top level) above its
  files. Each folder row: name, file and subfolder counts, who made it, its description,
  "For:" chips, a "For you" badge (or "In a folder for you" when a folder above it is for
  you), and a menu: Open, Rename, Move to folder…, Change who it's for, Delete folder.
  Opening one keeps it in the URL (`?folder=<HD Project Folder name>`), so a reload or a
  notification link lands there; the breadcrumb shows the whole path ("Files / Clients /
  Prompts") and each part links back up. Inside a folder, its description and "For:" chips
  sit under the breadcrumb and a **Folder** menu holds its actions.
- **New folder** (`ProjectFolderDialog.vue`: name, optional description, the For picker)
  makes a folder inside the open one, or at the top level. It is hidden at the deepest level.
  Rename uses the same dialog without the picker.
- **Add files** opens `UploadProjectFilesDialog.vue` for the open folder: **Choose files**,
  **Upload folder** (an `<input webkitdirectory>`), or drop files or whole folders in the
  dialog or anywhere on the Files page (which opens the dialog with them; dropped folders are
  read with `webkitGetAsEntry` and walked recursively). Hidden and system files (`.DS_Store`,
  `Thumbs.db`, `desktop.ini`, anything starting with `.`, and everything in a folder starting
  with `.`) are skipped. One upload takes at most 200 files (`MAX_UPLOAD_FILES`, shown in the
  dialog); extra files are left out with a notice. Files over the site's limit are flagged
  before upload. A folder upload first recreates its folder structure inside the open folder
  (`create_folder_paths`; a folder with the same name in the same place is reused), then
  uploads each file into its folder. Each file shows its own state (uploading, added, or the
  server's error) and the footer counts "Uploading n of m"; files go one at a time so one
  failure doesn't stop the rest, and the dialog stays open while something failed. The
  **For** picker (`FileForPicker.vue`, checkboxes of the project team) applies to every file
  in that upload. When it's done the dialog calls `notify_folder_upload` once for the batch.
- **List**: icon by type, file name, size, who added it, when, and "For:" chips
  (`PeopleChips.vue`). Files for the current user get a "For you" badge, files in a folder
  for them (or below one) an "In a folder for you" badge, and both a tinted row. **For me**
  lists those files from every folder, each with its folder path as a link. Row actions:
  View (Markdown, text, PDF, images) and Download, plus a menu with Change who it's for,
  Move to folder…, and Delete file (with a confirmation).
- **Move to folder…** (`MoveToFolderDialog.vue`) works for files and folders: a tree of the
  project's folders plus "Files (top level)". For a folder, the folder itself, its
  subfolders, and places that would make the tree deeper than five levels aren't offered.
- **Drag to move**: a file or folder row can be dragged onto a folder row or a breadcrumb
  part ("Files" = the top level). Only rows the person may move are draggable (the uploader
  or folder creator, the lead, managers, admins), and not in "For me". The target under the
  pointer gets a gray ring; while a folder is dragged, folders it can't go into (itself, its
  subfolders, too deep) are dimmed and refuse the drop. The drop calls the same
  `move_project_file` / `move_project_folder` API with a spinner on the target (no optimistic
  move), then reloads; the result is toasted and announced in an `aria-live` region ("Moved
  STATUS-REPORT.md to Prompts"). In-app drags carry the type
  `application/x-tbo-project-item` and never open the upload dialog; only drags that carry
  `Files` (from the computer) are uploads. Drag is never the only way: "Move to folder…" in
  each menu does the same by keyboard and on touch screens. Multi-select is not built.
- **Viewer** (`ProjectFileViewer.vue`):
  - `.md` / `.markdown`: rendered Markdown. `marked` turns it into HTML and `sanitize-html`
    keeps only harmless markup (no scripts, styles, images or event handlers; links open in a
    new tab with `noopener`), because files are user content. **Copy text** copies the raw
    file, which is what you paste a master prompt from.
  - `.txt`: shown as plain text, with Copy text.
  - PDF: the browser's PDF viewer in the dialog, plus **Open in new tab**.
  - Images: a preview.
  - Everything else: the file name and the Download action download it.
- Notifications open the Files tab of the project, in the folder they are about.

## Who can do what

| Action | Who |
| --- | --- |
| List, view, download | Anyone who can read the project: admins (System Manager, Agent Manager), the project's managers (creator, or "Project Manager" role on the project), the lead, members, and people with a task in it |
| Upload | The same people (`can_add_tasks`): the owner wants to share prompts, and members contributing files (designs, notes) is useful |
| Change who a file is for, move it | The person who added it, the project lead, the project's managers, admins |
| Delete a file | The person who added it, the project lead, the project's managers, admins |
| See folders | Anyone who can read the project |
| Make a folder, upload into any folder, upload a folder | The same people as Upload |
| Rename, move, change who a folder is for, delete it | The person who made it, the project lead, the project's managers, admins |

A file's "For" and its folder's "For" are independent: moving a file doesn't change who it is
for, and a folder's list doesn't copy onto its files. A folder's list does reach down the
tree for **For me** and for upload notifications.

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

## Folders

- **Nesting**: up to `MAX_DEPTH` = 5 levels (top-level folders are level 1). Deep enough for
  client / workstream / topic trees, shallow enough to stay findable. A folder can't be moved
  into itself or one of its subfolders, and a move that would push its deepest subfolder past
  level 5 is refused.
- **Names** are trimmed (runs of spaces collapse), can't contain `/` (it separates folder
  upload paths), and are unique among the folders in the same place, ignoring case (MariaDB
  compares case-insensitively). The same name is fine in another folder.
- **Delete moves the contents up**: a deleted folder's files and subfolders move to its
  parent (or the top level). Nothing is deleted with it, so there is no "folder not empty"
  dead end and no data loss. When a subfolder's name is already taken one level up, the
  delete is refused and says which one to rename. The confirmation says what will move and
  where.
- **Deleting a project** deletes its folders, deepest first, from `Project.on_trash`; its
  files go with the project's attachments.

## Data model

- **HD Project File** (`helpdesk/helpdesk/doctype/hd_project_file`): one per uploaded file.
  `project` (Link Project), `file` (Link File, unique), `file_name` (fetched from the File),
  `folder` (Link HD Project Folder; empty = the top level), `for_users` (Table → **HD Project
  File User**: `user` Link User, `full_name` fetched).
  Only System Manager has role access; everything else goes through the API.
  - `validate`: the File must be attached to that project; the folder must be on the same
    project; `for_users` must be on the project team; duplicates are dropped.
  - `on_update` (also runs on insert): people added to `for_users` since the last save are
    notified, except the person making the change.
- **HD Project Folder** (`helpdesk/helpdesk/doctype/hd_project_folder`): `project`,
  `folder_name`, `parent_folder` (Link to itself; empty = the top level), `description`, and
  `for_users` (the same **HD Project File User** child table; rows are told apart by
  `parenttype`). The creator is the document's `owner`. System Manager only, like HD Project
  File.
  - `validate`: name rules, parent on the same project, no cycles, depth, unique name, and
    `for_users` on the team (the `ProjectShare` mixin in `hd_project_file.py`, shared by
    files and folders).
  - `on_update`: people newly added to `for_users` are notified.
  - `on_trash`: moves the contents up (see Folders).
  - `FolderTree` (same module) loads a project's folders once and answers paths, depth,
    subtrees and who a folder or any folder above it is for; the list API, the move checks
    and the upload notifications all use it.
- Why a separate doctype and not a field on File: the "For" list needs a child table (a JSON
  list in a custom field was ruled out), and File is a core doctype; a small wrapper keeps the
  File untouched and lets the list be queried with a join.
- Files attached to a project without an HD Project File (e.g. uploaded from `/app`) still
  show in the list with an empty "For"; changing who they are for creates the record.
- Training sign-offs save their signed PDFs and the project completion letter on the
  project the same way ([project-signoff.md](project-signoff.md)), so they show here with an
  empty "For". A signed PDF is linked from its sign-off, so it can't be deleted while the
  sign-off exists.
- Deleting a File removes its HD Project File (`HelpdeskFile.on_trash` in
  `helpdesk/overrides/file.py`). Deleting a project deletes its attachments, and with them
  their records; `HD Project File` is in `ignore_links_on_delete` so its link to the project
  doesn't block that.

## Notifications

All go through `helpdesk.work_reminders.notify_users`: an HD Notification in the bell, then
delivered by `HDNotification.deliver`. **How the channel is chosen**: when HD Chat Settings is
enabled with platform **Microsoft Teams** and a Direct Message Workflow URL, the person gets a
Teams chat message from the Flow bot (`helpdesk.chat_notifications.send_direct`, matched by
email); when chat is off they get an email (unless they turned email notifications off); when
chat is on but can't reach them (no direct-message workflow), they get the email only if
"email when unreachable" is set. Slack works the same way. `notify_users` skips anyone who
already has that exact notification for the same document, so re-adding someone or repeating
a call doesn't notify them again.

- **A file's "For"**: "<who> shared <file name> with you in <project>", to people newly added
  (not the person making the change), linking to the Files tab.
- **A folder's "For"**: "<who> shared folder '<name>' with you in <project>", to people newly
  added, linking to `/projects/<project>/files?folder=<folder>`.
- **Files added to folders** (an upload into a folder, a folder upload, or moving a file into
  a folder by menu or drag): everyone the file's folder **or any folder above it** is for
  hears about it, except the person who added it and people the file itself is marked for
  (they already got the file notification). Each person gets **one** notification per upload
  batch however many files and folders it touched: "<who> added <file name | N files> to
  folder '<folder>' in <project>", naming and linking the deepest folder that holds all of
  that person's files. The dialog calls `notify_folder_upload` once after the batch; it only
  counts files the caller added, so it can't announce someone else's. Moving a folder
  notifies nobody.

## API (`helpdesk/api/project_files.py`)

Every call checks read access on the project first, and every call that names a file or a
folder refuses one that isn't on that project (`PermissionError`).

- `list_project_files(project, folder=None, for_me=False)` (GET): `{files, folders, folder,
  total, team, can_upload, max_file_size, max_depth, max_upload_files}`. `files` are the
  files in `folder` (the top level when empty), or with `for_me` the user's files from every
  folder. Each file: `name`, `project_file`, `file_name`, `file_url`, `file_size`,
  `uploaded_by`, `uploaded_by_name`, `creation`, `folder`, `folder_path`
  (`[{name, folder_name}]`, top first), `for_users` (`[{user, full_name}]`), `is_for_me`,
  `shared_via_folder`, `can_delete`, `can_edit_for`. `folders` is every folder, parents
  before subfolders: `name`, `folder_name`, `parent_folder`, `depth`, `height`,
  `description`, `created_by`, `created_by_name`, `creation`, `file_count`, `folder_count`,
  `for_users`, `is_for_me`, `for_me_via_parent`, `can_change`. `folder` is the open one plus
  its `path`. A folder that no longer exists is a `DoesNotExistError`.
- `upload_project_file(project, for_users=None, folder=None)` (POST, multipart field
  `file`): saves one file, in `folder` when given. `for_users` is a JSON list of users. Uses
  `add_project_file(project, file_name, content, for_users, folder)`, which tests call
  directly.
- `set_project_file_for(project, file, for_users)` (POST): replaces the "For" list.
- `move_project_file(project, file, folder=None)` (POST): into a folder or the top level.
- `create_project_folder(project, folder_name, description=None, for_users=None,
  parent_folder=None)`, `update_project_folder(project, folder, folder_name,
  description=None)`, `move_project_folder(project, folder, parent_folder=None)`,
  `set_project_folder_for(project, folder, for_users)`, `delete_project_folder(project,
  folder)` (all POST).
- `create_folder_paths(project, paths, parent_folder=None)` (POST): for a folder upload,
  makes or reuses the folders in `paths` (`"Clients/Acme"`) and returns `{path: folder}`; at
  most 200 paths.
- `notify_folder_upload(project, files)` (POST): the one notification batch after an
  upload.
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

`helpdesk/tests/test_project_folders.py` (helpers `make_project_folder`, and
`make_project_file` with `folder`): names trimmed and unique within their parent, nesting up
to five levels and the depth check on moves, no moving a folder into itself or below itself,
folder "For" notified once, one upload notification per person across a folder and its
ancestors (not the uploader, not repeated, not for someone else's files), no double
notification for people a file is marked for, a folder upload recreating and reusing its
structure (and the 200 limit), moving files (only the uploader or managers), deleting a folder
moving its contents up (and refusing on a name clash), the permission matrix (outsider,
member, creator, manager, admin) for every folder action including moves, "For me" inheriting
down the tree, and deleting a project deleting its nested folders.

Not covered by folders yet: the Home page's "Files for you" (`helpdesk/api/home.py`) lists
only files marked for the user directly, not files in folders shared with them.

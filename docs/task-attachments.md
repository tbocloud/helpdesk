# Task attachments: images and videos

People attach screenshots and screen recordings to a task, so they can show an issue instead
of only describing it. Only images and videos are taken. Everyone who can see the task sees
them. Files for the whole project (briefs, prompts, PDFs) belong in
[project files](project-files.md) instead.

## Where it is in the app

- **Task details** (`TaskDetailDialog.vue`, see [workspace-pages.md](workspace-pages.md)): an
  **Images and videos** section under the description (`components/TaskAttachments.vue`).
  - **Heading**: the count, and an **Add** button for people who may upload. Add opens the
    file picker (several files at once), limited to the allowed types. Files can also be
    dropped on the section, which shows a brand ring while files are dragged over it.
  - **Grid**: three columns (four from `sm`), square tiles. Images show with `object-cover`
    and their file name as alt text. Videos show their first frame (`<video
    preload="metadata">` at `#t=0.1`) under a play icon. Each tile is a button: "Open
    <name>" or "Play <name>".
  - **Uploads**: one at a time, each with its name and a progress bar
    (`FileUploadHandler`'s progress events). A refused file stays in the list with the reason
    and a dismiss button; the others still upload. A toast says how many were added.
  - **Hint** under the grid (for uploaders): the allowed types and both limits in MB, and
    that files can be dropped. The types and limits come from the server
    (`list_task_attachments`), so the browser and server checks can't drift apart.
  - **States**: a skeleton grid while loading; "Couldn't load the images and videos." with
    Retry; "No images or videos yet." (plus "Add a screenshot or a screen recording to show
    the issue." for uploaders).
  - Adding or removing a file reloads the task's **Activity** (a "Attached <name>" or
    "Removed <name>" note) and tells the opener the task changed, so a board reloads its
    count.
- **Lightbox** (`desk/src/components/MediaLightbox.vue`): a frappe-ui `Dialog` (size `4xl`)
  over the task details, titled with the file name. It traps focus and Esc closes it (only
  the lightbox; the task details stay open). Left and right arrows, and the Previous / Next
  buttons, step through the task's files and wrap around; the arrows are left alone while a
  video, input or text field has focus, so they still seek. "2 of 5", who added it and the
  size sit above the media. Videos play with native controls. **Download** (right) uses
  `downloadHref` from `projectFiles.ts`, so S3 files save instead of opening. **Remove**
  (left, away from Download) for people who may delete asks "Remove it for everyone?" with
  Keep / Remove file; after removing, the lightbox shows the next file or closes when none
  is left. The component takes generic `MediaItem`s, so other screens can reuse it.
- **Board cards** (`Kanban.vue`): an image icon and the count, when the task has any.

## What can be attached

| Kind | Extensions | Limit (`helpdesk/api/task_attachments.py`) |
| --- | --- | --- |
| Image | png, jpg, jpeg, webp, gif | `MAX_IMAGE_BYTES` = 10 MB |
| Video | mp4, webm, mov | `MAX_VIDEO_BYTES` = 50 MB |

- **Type check (server)**: `check_media` takes the extension (any case) and then reads the
  file's first bytes (`sniff_format`): PNG `89 50 4E 47 0D 0A 1A 0A`, JPEG `FF D8 FF`, GIF
  `GIF87a`/`GIF89a`, WebP `RIFF....WEBP`, WebM `1A 45 DF A3` (EBML), and MP4/MOV an ISO
  BMFF box (`ftyp` at byte 4, or an old QuickTime file's `moov`, `mdat`, `wide`, `free`,
  `skip` or `pnot`). The bytes must match the extension: a program renamed to `.png`, a JPEG
  saved as `.png` or an MP4 renamed to `.webm` is refused with "<name> isn't a real PNG
  file. Export it again and attach that." MP4 and MOV share a container, so either name
  passes for either. SVG is not taken: it can carry scripts.
- **Size**: the limit for the file's kind, capped by the site's own limit
  (`upload_limits()` = `min(MAX_*_BYTES, get_max_file_size())`). The browser checks the same
  numbers (returned by `list_task_attachments`) before sending a file and says what to do
  ("Trim the recording and try again").
- **The site limit comes first.** Frappe sets the request's `max_content_length` to the site's
  Max File Size (System Settings, else `max_file_size` in site config, else 25 MB), so a
  bigger request is refused before this module runs. That is why the limits shown are
  capped by it: on a site left at 25 MB, videos are limited to 25 MB. **Owner setting:** to
  take 50 MB videos, set System Settings → Max File Size to 50 (MB), and check that the
  server's nginx `client_max_body_size` allows at least 50m.

## Who can do what

| Action | Who | Where |
| --- | --- | --- |
| See the files, open, download | Anyone who can read the task | `list_task_attachments`; Frappe's File permission |
| Add | Whoever may change the task: its assignees, the project's lead, managers and coordinators, admins (Task write permission, `task_has_permission`) | `can_upload` |
| Remove | The person who added it, the project's lead and managers, admins | `delete_task_attachment` |

People who only see the task (a Project Manager on the team who isn't on it, a teammate who
sees all tasks) can look but not add: a screenshot is part of the work on the task, so it
comes from the people doing or running it. They can still comment.

### How opening a private file is authorised

Each file is a private Frappe File attached to the Task. `/private/files/...` and the S3
route `helpdesk.storage.s3.download` both call `File.is_downloadable()`, which for an
attached private file checks read permission on the Task, i.e. `task_has_permission`
(`helpdesk/tasky/permissions.py`). So an assignee and the project's managers can open it,
and someone outside the project (or behind a department wall) can't. The uploader can
always open their own file (Frappe's owner rule). There is no File `has_permission` hook.

## Storage

- `add_task_attachment` inserts a File (`attached_to_doctype = "Task"`, `is_private = 1`)
  with `ignore_permissions`, after its own checks, so the site's File rules (size,
  duplicate content reuse) apply as for any attachment.
- **S3 (HD File Storage Settings)**: the File `after_insert` hook moves new attachments to the
  bucket when their document type is listed. **Owner setting:** add **Task** to the settings'
  document types to keep task images and videos in the bucket. Their `file_url` becomes the
  download route, which the grid and lightbox use as is (`<video>` follows the redirect to
  the signed URL).
- Deleting a task deletes its files (Frappe removes a document's attachments).
- Thumbnails are the full image scaled by the browser (`loading="lazy"`); there is no
  separate thumbnail file.

## API (`helpdesk/api/task_attachments.py`)

| Method | Notes |
| --- | --- |
| `list_task_attachments(task)` | `{attachments: [{name, file_name, file_url, file_size, kind, uploaded_by, uploaded_by_name, creation, can_delete}], can_upload, limits: {image, video}, extensions: {image, video}}`, newest first. Only images and videos; any other file attached to the task elsewhere is left out. |
| `upload_task_attachment(task)` | POST, multipart field `file` (frappe-ui `FileUploadHandler` with `upload_endpoint`; its own `folder`, `is_private` fields are ignored). Returns `{name, file_url, kind}`. |
| `delete_task_attachment(task, file)` | POST. Refuses a file attached to another task. |
| `attachment_counts(tasks)` | Not whitelisted. `{task: count}` of images and videos, used by `get_kanban_tasks` for `attachment_count` on each card. |

Adding and removing write an Info comment on the task ("Attached <name>", "Removed
<name>"), which the activity shows as a note.

## Tests

`helpdesk/tests/test_task_attachments.py` (helper `make_task_attachment` in
`helpdesk/test_utils.py`): an assignee attaches an image and a video privately and the list
shape, every allowed format, refused types and renamed files, the per-kind limit and the site
cap, an outsider can't list, upload or open (`is_downloadable`) while assignees and the
manager can, someone who only sees the task can't upload, removal rules, a file from another
task, the multipart endpoint through `frappe.call`, and the board count.

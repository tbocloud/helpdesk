"""Keep chosen attachments in an S3 bucket instead of on this server.

Every File sent to the bucket carries its object key in `hd_s3_key`. With
"Keep a copy on this server" (the default) nothing else changes: the file stays
on disk and is served from there, and the bucket holds a second copy. Without
it, the local copy is removed and `file_url` points at `download` below, so everything that links to a file
(thumbnails, attachment lists) keeps working. Opening that URL checks the
viewer's access to the File first and only then hands out a short-lived signed
link. Code that needs the bytes (zip downloads, the client portal, the client
ERP sync) calls `File.get_content()`, which `HelpdeskFile` serves from S3.

Only new files attached to the configured document types go to the bucket;
`move_existing_files` sends the older ones there too.
"""

import mimetypes
import os
from urllib.parse import quote

import frappe
from frappe import _

SETTINGS = "HD File Storage Settings"
KEY_FIELD = "hd_s3_key"
DOWNLOAD_PATH = "/api/method/helpdesk.storage.s3.download"
MOVE_BATCH = 500


# ---------------------------------------------------------------- settings --


def get_settings():
    return frappe.get_cached_doc(SETTINGS)


def is_enabled(settings=None) -> bool:
    settings = settings or get_settings()
    return bool(settings.enabled and settings.bucket) and not real_bucket_blocked()


def real_bucket_blocked() -> bool:
    """Tests never reach a real bucket: only those that switch on the fake one use storage."""
    return bool(frappe.flags.in_test and not frappe.flags.hd_fake_s3)


def stored_doctypes(settings=None) -> set[str]:
    settings = settings or get_settings()
    return {row.document_type for row in settings.document_types}


def get_client(settings=None):
    import boto3
    from botocore.config import Config

    settings = settings or get_settings()
    return boto3.client(
        "s3",
        region_name=settings.region or None,
        endpoint_url=settings.endpoint_url or None,
        aws_access_key_id=settings.access_key_id,
        aws_secret_access_key=settings.get_password(
            "secret_access_key", raise_exception=False
        ),
        # signed links must use the region's own host, or the bucket rejects them
        config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
    )


# ----------------------------------------------------------------- upload --


def object_key(file_doc, settings=None) -> str:
    settings = settings or get_settings()
    prefix = (settings.key_prefix or frappe.local.site).strip("/")
    parts = [prefix, frappe.scrub(file_doc.attached_to_doctype or "unattached")]
    if file_doc.attached_to_name:
        parts.append(str(file_doc.attached_to_name))
    # the File name keeps two uploads with the same file name apart
    parts.append(f"{file_doc.name}-{file_doc.file_name}")
    return "/".join(parts)


def download_url(file_doc) -> str:
    return f"{DOWNLOAD_PATH}?file={quote(file_doc.name)}"


def should_store(file_doc, settings=None) -> bool:
    settings = settings or get_settings()
    return bool(
        is_enabled(settings)
        and not file_doc.is_folder
        and not file_doc.get(KEY_FIELD)
        and file_doc.file_url
        and file_doc.file_url.startswith(("/files/", "/private/files/"))
        and file_doc.attached_to_doctype in stored_doctypes(settings)
    )


def upload(file_doc, settings=None) -> bool:
    """Send a local file to the bucket and point the File at it; on failure the file stays local."""
    settings = settings or get_settings()
    if not should_store(file_doc, settings):
        return False

    local_path = file_doc.get_full_path()
    local_url = file_doc.file_url
    key = object_key(file_doc, settings)
    try:
        content_type = (
            mimetypes.guess_type(file_doc.file_name or "")[0]
            or "application/octet-stream"
        )
        get_client(settings).upload_file(
            local_path,
            settings.bucket,
            key,
            ExtraArgs={"ContentType": content_type},
        )
    except Exception:  # noqa: BLE001 - a bucket problem must never lose the upload
        frappe.log_error(
            title=f"S3 upload failed for {file_doc.name}",
            message=frappe.get_traceback(),
        )
        return False

    if settings.keep_local_copy:
        # the bucket is a second copy; the file is still served from this server
        file_doc.db_set(KEY_FIELD, key, update_modified=False)
        return True
    file_doc.db_set(
        {KEY_FIELD: key, "file_url": download_url(file_doc)}, update_modified=False
    )
    remove_local_copy(local_url, local_path, file_doc.name)
    return True


def remove_local_copy(local_url: str, local_path: str, file_name: str):
    # Frappe reuses one copy on disk for identical uploads; keep it while anyone points at it
    still_used = frappe.db.exists(
        "File", {"file_url": local_url, "name": ("!=", file_name)}
    )
    if not still_used and os.path.exists(local_path):
        os.remove(local_path)


def after_insert(file_doc, method=None):
    """File hook: new attachments of the chosen document types go straight to the bucket."""
    upload(file_doc)


# --------------------------------------------------------------- download --


def signed_url(file_doc, settings=None, *, as_attachment: bool = False) -> str:
    settings = settings or get_settings()
    params = {"Bucket": settings.bucket, "Key": file_doc.get(KEY_FIELD)}
    content_type = mimetypes.guess_type(file_doc.file_name or "")[0]
    if content_type:
        params["ResponseContentType"] = content_type
    disposition = "attachment" if as_attachment else "inline"
    params[
        "ResponseContentDisposition"
    ] = f"{disposition}; filename*=UTF-8''{quote(file_doc.file_name or 'file')}"
    return get_client(settings).generate_presigned_url(
        "get_object", Params=params, ExpiresIn=settings.link_expiry_seconds or 600
    )


def read(file_doc, settings=None) -> bytes:
    settings = settings or get_settings()
    response = get_client(settings).get_object(
        Bucket=settings.bucket, Key=file_doc.get(KEY_FIELD)
    )
    return response["Body"].read()


# public files open like /files/ do; File.is_downloadable checks the rest
@frappe.whitelist(allow_guest=True, methods=["GET"])  # nosemgrep
def download(file: str, download: int | str = 0):
    """Open a stored file: same access rules as Frappe's own files, then a short-lived link."""
    if not frappe.db.exists("File", file):
        raise frappe.DoesNotExistError(_("File not found"))
    file_doc = frappe.get_doc("File", file)
    if not file_doc.get(KEY_FIELD):
        frappe.local.response["type"] = "redirect"
        frappe.local.response["location"] = file_doc.file_url
        return
    if not file_doc.is_downloadable():
        raise frappe.PermissionError(_("You can't open this file."))
    frappe.local.response["type"] = "redirect"
    frappe.local.response["location"] = signed_url(
        file_doc, as_attachment=frappe.utils.cint(download)
    )


# ----------------------------------------------------------------- delete --


def delete_object(file_doc, settings=None):
    settings = settings or get_settings()
    key = file_doc.get(KEY_FIELD)
    if (
        not key
        or not settings.bucket
        or not settings.delete_from_bucket
        or real_bucket_blocked()
    ):
        return
    if frappe.db.exists("File", {KEY_FIELD: key, "name": ("!=", file_doc.name)}):
        return
    try:
        get_client(settings).delete_object(Bucket=settings.bucket, Key=key)
    except (
        Exception
    ):  # noqa: BLE001 - the File is gone either way; keep a trace to clean up
        frappe.log_error(
            title=f"S3 delete failed for {key}", message=frappe.get_traceback()
        )


# ------------------------------------------------------------ admin tools --


@frappe.whitelist(methods=["POST"])
def test_connection() -> dict:
    """Write, read and delete a small object, so a wrong key or policy shows up now, not on upload."""
    frappe.only_for("System Manager")
    settings = frappe.get_doc(SETTINGS)
    if not (
        settings.bucket
        and settings.access_key_id
        and settings.get_password("secret_access_key", raise_exception=False)
    ):
        return {
            "ok": False,
            "message": _("Fill in the bucket, region and both keys, save, then test."),
        }
    key = f"{(settings.key_prefix or frappe.local.site).strip('/')}/.helpdesk-connection-test"
    try:
        client = get_client(settings)
        client.put_object(Bucket=settings.bucket, Key=key, Body=b"ok")
        assert (
            client.get_object(Bucket=settings.bucket, Key=key)["Body"].read() == b"ok"
        )
        client.delete_object(Bucket=settings.bucket, Key=key)
        ok, message = True, _("Connected. Uploading, reading and deleting all work.")
    except Exception as e:  # noqa: BLE001 - the message is the result
        ok, message = False, _("Couldn't use the bucket: {0}").format(str(e)[:300])
    frappe.db.set_single_value(
        SETTINGS,
        {
            "last_test_on": frappe.utils.now_datetime(),
            "last_test_ok": int(ok),
            "last_test_result": message,
        },
    )
    return {"ok": ok, "message": message}


@frappe.whitelist()
def get_overview() -> dict:
    frappe.only_for("System Manager")
    doctypes = list(stored_doctypes(frappe.get_doc(SETTINGS)))
    if not doctypes:
        return {"in_bucket": 0, "local": 0}
    base = {"attached_to_doctype": ("in", doctypes), "is_folder": 0}
    return {
        "in_bucket": frappe.db.count("File", {**base, KEY_FIELD: ("is", "set")}),
        "local": frappe.db.count(
            "File",
            {**base, KEY_FIELD: ("is", "not set"), "file_url": ("like", "%/files/%")},
        ),
    }


@frappe.whitelist(methods=["POST"])
def move_existing_files():
    """Queue sending the chosen document types' existing local attachments to the bucket."""
    frappe.only_for("System Manager")
    if not is_enabled(frappe.get_doc(SETTINGS)):
        frappe.throw(_("Turn on S3 storage and test the connection first."))
    frappe.enqueue(
        "helpdesk.storage.s3.move_existing_files_job",
        queue="long",
        timeout=4 * 60 * 60,
        job_id="helpdesk-move-files-to-s3",
        deduplicate=True,
    )
    return {"queued": True}


def move_existing_files_job(extra_filters: dict | None = None):
    settings = frappe.get_doc(SETTINGS)
    doctypes = list(stored_doctypes(settings))
    if not is_enabled(settings) or not doctypes:
        return
    names = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": ("in", doctypes),
            "is_folder": 0,
            KEY_FIELD: ("is", "not set"),
            **(extra_filters or {}),
        },
        pluck="name",
        limit=MOVE_BATCH,
    )
    moved = 0
    for name in names:
        if upload(frappe.get_doc("File", name), settings):
            moved += 1
            frappe.db.commit()  # nosemgrep - each file is done once its bytes are in the bucket
    if moved == MOVE_BATCH:
        # more to go: run again rather than hold one job for hours
        frappe.enqueue(
            "helpdesk.storage.s3.move_existing_files_job",
            queue="long",
            extra_filters=extra_filters,
        )

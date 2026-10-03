from frappe.core.doctype.file.file import File

from helpdesk.storage import s3


class HelpdeskFile(File):
    """Frappe's File, plus files kept in the S3 bucket (see helpdesk.storage.s3).

    Files on this server behave exactly as before, including those that also
    have a copy in the bucket. Only a File kept *only* in the bucket skips the
    on-disk checks and reads its bytes from there.
    """

    @property
    def has_bucket_copy(self) -> bool:
        return bool(self.get(s3.KEY_FIELD))

    @property
    def in_bucket(self) -> bool:
        """Kept only in the bucket: its URL is the download route, not a local path."""
        return self.has_bucket_copy and not (self.file_url or "").startswith(
            ("/files/", "/private/files/")
        )

    def validate_file_path(self):
        if not self.in_bucket:
            super().validate_file_path()

    def validate_file_url(self):
        if not self.in_bucket:
            super().validate_file_url()

    def validate_file_on_disk(self):
        # a missing local copy is fine while the bucket still has the file
        if self.in_bucket or (self.has_bucket_copy and not super().exists_on_disk()):
            return
        super().validate_file_on_disk()

    def handle_is_private_changed(self):
        # bucket objects are always private; moving between public/private folders is a disk thing
        if not self.in_bucket:
            super().handle_is_private_changed()

    def exists_on_disk(self):
        return False if self.in_bucket else super().exists_on_disk()

    def get_content(self) -> bytes:
        if self.get("content"):
            return super().get_content()
        # a lost local copy is read back from the bucket
        if self.in_bucket or (self.has_bucket_copy and not super().exists_on_disk()):
            self._content = s3.read(self)
            return self._content
        return super().get_content()

    def _delete_file_on_disk(self):
        if self.has_bucket_copy:
            s3.delete_object(self)
        if not self.in_bucket:
            super()._delete_file_on_disk()

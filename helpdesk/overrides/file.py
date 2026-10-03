from frappe.core.doctype.file.file import File

from helpdesk.storage import s3


class HelpdeskFile(File):
    """Frappe's File, plus files kept in the S3 bucket (see helpdesk.storage.s3).

    Files on this server behave exactly as before; only a File with an S3 key
    skips the on-disk checks and reads its bytes from the bucket.
    """

    @property
    def in_bucket(self) -> bool:
        return bool(self.get(s3.KEY_FIELD))

    def validate_file_path(self):
        if not self.in_bucket:
            super().validate_file_path()

    def validate_file_url(self):
        if not self.in_bucket:
            super().validate_file_url()

    def validate_file_on_disk(self):
        if not self.in_bucket:
            super().validate_file_on_disk()

    def handle_is_private_changed(self):
        # bucket objects are always private; moving between public/private folders is a disk thing
        if not self.in_bucket:
            super().handle_is_private_changed()

    def exists_on_disk(self):
        return False if self.in_bucket else super().exists_on_disk()

    def get_content(self) -> bytes:
        if self.in_bucket and not self.get("content"):
            self._content = s3.read(self)
            return self._content
        return super().get_content()

    def _delete_file_on_disk(self):
        if self.in_bucket:
            s3.delete_object(self)
        else:
            super()._delete_file_on_disk()

# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

from frappe.model.document import Document

EXPO_TOKEN_PREFIXES = ("ExponentPushToken[", "ExpoPushToken[")


class HDMobileDevice(Document):
    def before_validate(self):
        self.set_token_type()

    def set_token_type(self):
        self.token_type = self.token_type_of(self.token)

    @staticmethod
    def token_type_of(token: str | None) -> str:
        """Expo push tokens look like ExponentPushToken[…]; anything else is a raw FCM token."""
        return "Expo" if (token or "").startswith(EXPO_TOKEN_PREFIXES) else "FCM"

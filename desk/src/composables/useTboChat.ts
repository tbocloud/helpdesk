import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { computed } from "vue";
import LucideMessagesSquare from "~icons/lucide/messages-square";

const SIGN_IN = "/api/method/helpdesk.api.chatwoot_sso.login";

/**
 * "Open TBO Chat" for the desktop and mobile profile menus: TBO Chat signs agents
 * in through TBO Support (docs/chatwoot-sso.md), so nobody needs a Chatwoot password.
 * Spread `menuItems` into a menu; it is empty for anyone who can't open TBO Chat.
 */
export function useTboChat() {
  const auth = useAuthStore();
  const menuItems = computed(() =>
    auth.canOpenChat
      ? [
          {
            label: __("Open TBO Chat"),
            icon: LucideMessagesSquare,
            onClick: () => window.open(SIGN_IN, "_blank", "noopener"),
          },
        ]
      : []
  );
  return { menuItems };
}

import { useAuthStore } from "@/stores/auth";
import { globalStore } from "@/stores/globalStore";
import { useDebounceFn } from "@vueuse/core";
import { onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

const currentViewers = reactive<Record<string, string[]> | null>({});

export function useActiveViewers(ticketId: string) {
  const { $socket } = globalStore();

  const { userId } = useAuthStore();
  $socket.on("ticket_viewers", (data: { ticket_id: string; users: string }) => {
    if (data.ticket_id === ticketId) {
      const viewers = JSON.parse(data.users).filter(
        (u: string) => u !== userId
      );
      currentViewers[ticketId] = viewers;
    }
  });

  const handleBeforeUnload = (_ticketId: string) => {
    $socket.emit("stop_view_ticket", _ticketId);
  };
  const startViewing = (_ticketId: string) => {
    $socket.emit("view_ticket", _ticketId);
    window.addEventListener("beforeunload", () =>
      handleBeforeUnload(_ticketId)
    );
  };

  const stopViewing = (_ticketId: string) => {
    $socket.emit("stop_view_ticket", _ticketId);

    window.removeEventListener("beforeunload", () =>
      handleBeforeUnload(_ticketId)
    );
  };

  return {
    currentViewers,
    startViewing,
    stopViewing,
  };
}

export function useNotifyTicketUpdate(ticketId: string) {
  const { $socket } = globalStore();
  const notifyTicketUpdate = (field: string, value: string) => {
    $socket.emit("notify_ticket_update", ticketId, field, value);
  };
  // how to check if $socket is already listening to avoid multiple listeners
  return { notifyTicketUpdate };
}

export function useTyping(ticketId: string) {
  const { $socket } = globalStore();
  const { userId } = useAuthStore();

  const typingCounter = ref(0);
  const isTyping = ref(false);
  const typingUsers = reactive<string[]>([]);
  let timeout: any = null;

  // Listen for typing events from other users
  $socket.on(
    "helpdesk_ticket_typing",
    (data: { ticket_id: string; user: string }) => {
      if (data.ticket_id === ticketId && data.user !== userId) {
        // Add user to typing list if not already present
        if (!typingUsers.includes(data.user)) {
          typingUsers.push(data.user);
        }
      }
    }
  );

  // Listen for typing stopped events
  $socket.on(
    "helpdesk_ticket_typing_stopped",
    (data: { ticket_id: string; user: string }) => {
      if (data.ticket_id === ticketId) {
        // Remove user from typing list
        const index = typingUsers.indexOf(data.user);
        if (index > -1) {
          typingUsers.splice(index, 1);
        }
      }
    }
  );

  const emitStartTyping = () => {
    $socket?.emit("helpdesk_ticket_typing", ticketId);
  };

  const emitStopTyping = () => {
    $socket?.emit("helpdesk_ticket_typing_stopped", ticketId);
  };

  const onUserType = () => {
    if (!isTyping.value) {
      isTyping.value = true;
      typingCounter.value = typingCounter.value + 1;
      emitStartTyping();
    }
  };

  // Reset the typing state after 10 seconds of inactivity
  // If agent is not typing for 10 seconds, we assume they have stopped typing
  watch(typingCounter, (newVal) => {
    if (timeout) {
      clearTimeout(timeout);
    }

    if (newVal > 0) {
      timeout = setTimeout(() => {
        isTyping.value = false;
        typingCounter.value = 0;
        emitStopTyping();
      }, 10000);
    }
  });

  const stopTyping = () => {
    emitStopTyping();
    isTyping.value = false;
    typingCounter.value = 0;
    if (timeout) {
      clearTimeout(timeout);
    }
  };

  const cleanup = () => {
    stopTyping();
    if (timeout) {
      clearTimeout(timeout);
    }
    // Remove socket listeners
    $socket.off("helpdesk_ticket_typing");
    $socket.off("helpdesk_ticket_typing_stopped");
  };

  return {
    stopTyping,
    onUserType,
    typingUsers,
    cleanup,
  };
}

// how many mounted pages listen to each doctype's room, so the last one leaves it
const listRooms: Record<string, number> = {};

/**
 * Reloads `resource`, debounced, when a record of `doctype` changes: Frappe's
 * `list_update`, sent on every save, and by helpdesk.tasky.api.notify_task_list
 * for task changes made without one (timer, assignment). A change arriving
 * while it loads reloads it once more afterwards, since that answer may predate
 * it. Joins the doctype's room while the calling component is mounted, and
 * again after a reconnect.
 */
export function useListUpdate(
  doctype: string,
  resource: { loading: boolean; reload: () => unknown },
  wait = 1500
) {
  const { $socket } = globalStore();
  let mounted = false;
  let pending = false;
  function onUpdate() {
    if (!mounted) return;
    if (resource.loading) pending = true;
    else resource.reload();
  }
  watch(
    () => resource.loading,
    (loading) => {
      if (loading || !pending || !mounted) return;
      pending = false;
      resource.reload();
    }
  );
  // a burst of changes is one reload, and a steady stream still reloads
  const reload = useDebounceFn(onUpdate, wait, { maxWait: 10_000 });
  const subscribe = () => $socket.emit("doctype_subscribe", doctype);
  const onListUpdate = (data: { doctype?: string }) => {
    if (data?.doctype === doctype) reload();
  };

  onMounted(() => {
    mounted = true;
    listRooms[doctype] = (listRooms[doctype] || 0) + 1;
    subscribe();
    $socket.on("connect", subscribe);
    $socket.on("list_update", onListUpdate);
  });
  onBeforeUnmount(() => {
    // a debounced reload may still be waiting
    mounted = false;
    $socket.off("connect", subscribe);
    $socket.off("list_update", onListUpdate);
    listRooms[doctype] -= 1;
    if (!listRooms[doctype]) $socket.emit("doctype_unsubscribe", doctype);
  });
}

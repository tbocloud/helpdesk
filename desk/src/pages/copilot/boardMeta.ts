// The Copilot board (Phase 10, helpdesk.api.copilot_board): shared helpers.
import { globalStore } from "@/stores/globalStore";
import { __ } from "@/translation";
import { useDebounceFn, useIntervalFn } from "@vueuse/core";
import { onBeforeUnmount, onMounted, watch } from "vue";

export const BOARD_API = "helpdesk.api.copilot_board";
// sent by the hub on any run's change: a signal only, each board asks again with its own permissions
const BOARD_EVENT = "helpdesk:copilot-board";

/**
 * Reloads `resource` when a run changes (debounced: a burst is one reload) and every minute,
 * while the calling component is mounted. A change arriving while it loads reloads it once more.
 */
export function useBoardRefresh(resource: {
  loading: boolean;
  reload: () => unknown;
}) {
  const { $socket } = globalStore();
  let mounted = false;
  let pending = false;
  function refresh() {
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
  const onChange = useDebounceFn(refresh, 1500, { maxWait: 10_000 });
  useIntervalFn(refresh, 60_000);
  onMounted(() => {
    mounted = true;
    $socket.on(BOARD_EVENT, onChange);
  });
  onBeforeUnmount(() => {
    mounted = false;
    $socket.off(BOARD_EVENT, onChange);
  });
}

/** "3 h", "2 d", "15 min": how long something has waited. */
export function waited(hours: number | null | undefined): string {
  if (hours === null || hours === undefined) return "-";
  if (hours < 1) return __("{0} min", String(Math.max(Math.round(hours * 60), 0)));
  if (hours < 48) return __("{0} h", String(Math.round(hours)));
  return __("{0} d", String(Math.round(hours / 24)));
}

export type BoardCard = {
  run: string;
  ticket: string;
  subject: string;
  customer: string;
  state: string;
  kind: string;
  root_cause: string;
  fix_status: string;
  shadow: boolean;
  source: string;
  waited_hours: number | null;
  waits_on: string;
  url: string;
};

export type BoardColumn = {
  key: string;
  label: string;
  count: number;
  cards: BoardCard[];
  more: number;
};

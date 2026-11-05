<template>
  <!-- the agent's tickets as a chat list (Phase 16): who, what about, the last message, and at
       most two signals; the queues and the search on top -->
  <aside
    class="flex h-full min-h-0 flex-col bg-surface-base"
    :aria-label="__('Tickets')"
  >
    <div class="space-y-2.5 px-4 pb-2 pt-3">
      <!-- with no ticket open the page header has the title, New ticket and Table -->
      <div v-if="showHeading" class="flex items-center justify-between gap-2">
        <h2 class="text-lg font-semibold text-ink-gray-9">
          {{ __("Tickets") }}
        </h2>
        <div class="flex items-center gap-1">
          <!-- frappe-ui's Button names itself from `label` (read out, not shown with an icon) -->
          <Button
            variant="ghost"
            :label="__('Table view')"
            :tooltip="__('Show the tickets as a table')"
            @click="ticketsLayout = 'table'"
          >
            <template #icon>
              <LucideTable class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            variant="ghost"
            :label="__('New ticket')"
            :tooltip="__('New ticket')"
            :route="{ name: 'TicketAgentNew' }"
          >
            <template #icon>
              <LucidePlus class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </div>
      </div>
      <div class="relative">
        <LucideSearch
          class="pointer-events-none absolute start-3 top-1/2 size-4 -translate-y-1/2 text-ink-gray-5"
          aria-hidden="true"
        />
        <input
          id="inbox-search"
          ref="searchRef"
          v-model="searchText"
          type="search"
          :aria-label="__('Search tickets')"
          :placeholder="__('Search name, customer, subject or #')"
          class="h-9 w-full rounded-full border border-outline-gray-2 bg-surface-gray-1 pe-9 ps-9 text-base text-ink-gray-9 placeholder:text-ink-gray-5 focus:border-outline-gray-4 focus:bg-surface-base focus:outline-none focus:ring-0"
          @keydown.esc="clearSearch"
        />
        <kbd
          v-if="!searchText"
          class="pointer-events-none absolute end-3 top-1/2 -translate-y-1/2 rounded border border-outline-gray-2 px-1 font-mono text-2xs text-ink-gray-5"
          aria-hidden="true"
          >/</kbd
        >
      </div>
      <div
        ref="chipsRef"
        class="hide-scrollbar -mx-4 flex gap-1.5 overflow-x-auto px-4 pb-0.5"
        role="group"
        :aria-label="__('Queues')"
      >
        <button
          v-if="inbox.queue === 'filtered'"
          type="button"
          class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border border-transparent bg-surface-gray-10 px-3 text-sm font-medium text-ink-base focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          aria-pressed="true"
          :title="__('Clear the link\'s filters')"
          @click="clearLinkFilters"
        >
          {{ __("Filtered") }}
          <LucideX class="size-3.5" aria-hidden="true" />
        </button>
        <button
          v-for="queue in QUEUES"
          :key="queue.key"
          type="button"
          :aria-pressed="inbox.queue === queue.key"
          :title="queue.hint"
          class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-full border px-3 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          :class="
            inbox.queue === queue.key
              ? 'border-transparent bg-surface-gray-10 font-medium text-ink-base'
              : 'border-outline-gray-2 text-ink-gray-8 hover:bg-surface-gray-2'
          "
          @click="pick(queue.key)"
        >
          {{ queue.label }}
          <span
            v-if="
              queue.key !== 'resolved' && inbox.counts[queue.key] !== undefined
            "
            class="min-w-5 rounded-full px-1.5 text-center font-mono text-2xs tabular-nums leading-5"
            :class="countClass(queue)"
          >
            {{ inbox.counts[queue.key] }}
          </span>
        </button>
      </div>
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-4">
      <div
        v-if="!inbox.loaded && !inbox.failed"
        class="space-y-1"
        aria-busy="true"
        :aria-label="__('Loading tickets')"
      >
        <div v-for="i in 6" :key="i" class="flex gap-3 px-2 py-3">
          <div
            class="size-9 shrink-0 animate-pulse rounded-full bg-surface-gray-2"
          />
          <div class="flex-1 space-y-2">
            <div class="h-3 w-2/3 animate-pulse rounded bg-surface-gray-2" />
            <div class="h-3 w-full animate-pulse rounded bg-surface-gray-2" />
            <div class="h-3 w-4/5 animate-pulse rounded bg-surface-gray-2" />
          </div>
        </div>
      </div>
      <TaskyState
        v-else-if="inbox.failed && !inbox.rows.length"
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the tickets')"
        :message="__('Check your connection and try again.')"
        error
      >
        <Button :label="__('Retry')" @click="loadInbox()" />
      </TaskyState>
      <div
        v-else-if="!inbox.rows.length"
        class="flex flex-col items-center gap-2 px-6 py-14 text-center"
      >
        <LucideInbox class="size-6 text-ink-gray-4" aria-hidden="true" />
        <p class="text-base font-medium text-ink-gray-8">{{ emptyText }}</p>
        <Button
          v-if="inbox.search || inbox.queue !== 'open'"
          :label="__('Show all open tickets')"
          @click="showAllOpen"
        />
      </div>
      <ul v-else ref="listRef" class="space-y-0.5" :aria-label="listLabel">
        <li v-for="row in inbox.rows" :key="row.name">
          <RouterLink
            :to="{ name: 'TicketAgent', params: { ticketId: row.name } }"
            :aria-current="isOpenRow(row) ? 'page' : undefined"
            class="flex gap-3 rounded-xl px-2.5 py-2.5 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
            :class="
              isOpenRow(row) ? 'bg-surface-gray-3' : 'hover:bg-surface-gray-2'
            "
          >
            <span class="relative mt-0.5 shrink-0">
              <Avatar size="xl" :label="who(row)" />
              <span
                v-if="isUnseen(row, userId)"
                class="absolute -end-0.5 -top-0.5 size-2.5 rounded-full border-2 border-surface-base bg-surface-gray-9"
                :title="__('Not opened by you yet')"
              />
            </span>
            <span class="min-w-0 flex-1">
              <span class="flex items-baseline gap-2">
                <span
                  class="truncate text-base text-ink-gray-9"
                  :class="
                    isUnseen(row, userId) ? 'font-semibold' : 'font-medium'
                  "
                  >{{ who(row) }}</span
                >
                <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-5">{{
                  row.customer || ""
                }}</span>
                <Tooltip :text="dateFormat(row.modified, dateTooltipFormat)">
                  <span class="shrink-0 text-xs tabular-nums text-ink-gray-5">{{
                    ago(row.modified)
                  }}</span>
                </Tooltip>
              </span>
              <span class="mt-0.5 flex min-w-0 items-center gap-1">
                <component
                  :is="priorityIcon(row.priority)"
                  v-if="['Urgent', 'High'].includes(row.priority)"
                  class="size-3.5 shrink-0"
                  :class="
                    row.priority === 'Urgent' ? 'text-danger' : 'text-warning'
                  "
                  :aria-label="__('{0} priority', __(row.priority))"
                />
                <span
                  class="truncate text-sm text-ink-gray-9"
                  :class="isUnseen(row, userId) && 'font-semibold'"
                  :title="row.subject"
                  >{{ row.subject }}</span
                >
              </span>
              <span class="mt-0.5 flex min-w-0 items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-sm text-ink-gray-6">
                  <template v-if="row.last">
                    <span class="font-medium text-ink-gray-8"
                      >{{ lastWho(row) }}:</span
                    >
                    {{ row.last.text }}
                  </template>
                  <template v-else>{{ __("No messages yet") }}</template>
                </span>
                <span
                  v-if="waiting(row)"
                  class="flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1.5 text-2xs font-semibold tabular-nums"
                  :class="
                    isUnseen(row, userId)
                      ? 'bg-surface-gray-10 text-ink-base'
                      : 'bg-surface-gray-3 text-ink-gray-7'
                  "
                  :title="__('Messages from the customer since our last reply')"
                >
                  {{ waiting(row) }}
                  <span class="sr-only">{{
                    __("messages from the customer since our last reply")
                  }}</span>
                </span>
              </span>
              <span
                v-if="signals(row).length || assignee(row)"
                class="mt-1.5 flex min-w-0 items-center gap-1.5"
              >
                <TaskyBadge
                  v-for="s in signals(row)"
                  :key="s.label"
                  :tone="s.tone"
                  :icon="s.icon"
                  class="min-w-0"
                >
                  <span class="truncate">{{ s.label }}</span>
                </TaskyBadge>
                <span
                  v-if="assignee(row)"
                  class="ms-auto shrink-0"
                  :title="__('Assigned to {0}', assigneeName(row))"
                >
                  <Avatar
                    size="xs"
                    :label="assigneeName(row)"
                    :image="getUser(assignee(row)).user_image"
                  />
                  <span class="sr-only">{{
                    __("Assigned to {0}", assigneeName(row))
                  }}</span>
                </span>
              </span>
            </span>
          </RouterLink>
        </li>
        <li v-if="inbox.more" class="px-2 pt-2">
          <Button
            class="w-full"
            :label="__('Show more')"
            :loading="inbox.loading"
            @click="loadInbox(true)"
          />
        </li>
      </ul>
    </div>
  </aside>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import type { Tone } from "@/components/tone";
import { useShortcut } from "@/composables/shortcuts";
import { useSlaTimeLeft } from "@/composables/useSlaTimeLeft";
import { priorityIcon } from "@/pages/tasky/taskMeta";
import { dueBadge, overdueFor } from "@/pages/ticket/ticketMeta";
import { useAuthStore } from "@/stores/auth";
import { globalStore } from "@/stores/globalStore";
import { useTicketStatusStore } from "@/stores/ticketStatus";
import { useUserStore } from "@/stores/user";
import { __ } from "@/translation";
import { dateFormat, dateTooltipFormat } from "@/utils";
import {
  useDebounceFn,
  useDocumentVisibility,
  useIntervalFn,
} from "@vueuse/core";
import { Avatar, Button, dayjs, dayjsLocal, Tooltip } from "frappe-ui";
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  type Component,
} from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideHourglass from "~icons/lucide/hourglass";
import LucideInbox from "~icons/lucide/inbox";
import LucidePause from "~icons/lucide/pause";
import LucidePlus from "~icons/lucide/plus";
import LucideReply from "~icons/lucide/reply";
import LucideSearch from "~icons/lucide/search";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideTable from "~icons/lucide/table";
import LucideUserX from "~icons/lucide/user-x";
import LucideX from "~icons/lucide/x";
import {
  chooseQueue,
  countQueues,
  firstName,
  inbox,
  isUnseen,
  loadInbox,
  QUEUES,
  refreshInbox,
  takeLinkFilters,
  ticketsLayout,
  type InboxRow,
  type Queue,
  type QueueKey,
} from "./inbox";

withDefaults(defineProps<{ showHeading?: boolean }>(), { showHeading: true });

const route = useRoute();
const router = useRouter();
const { userId } = useAuthStore();
const { getUser } = useUserStore();
const { getStatus } = useTicketStatusStore();
const searchRef = ref<HTMLInputElement | null>(null);
const listRef = ref<HTMLElement | null>(null);
const chipsRef = ref<HTMLElement | null>(null);

// --- queues and search ---------------------------------------------------------------------------
const searchText = ref(inbox.search);
const search = useDebounceFn(() => {
  inbox.search = searchText.value;
  loadInbox();
}, 300);
watch(searchText, search);

function clearSearch() {
  if (!searchText.value) return searchRef.value?.blur();
  searchText.value = "";
}

function pick(key: QueueKey) {
  if (inbox.queue === key) return;
  chooseQueue(key);
  dropLinkFilters();
}

function clearLinkFilters() {
  chooseQueue("open");
  dropLinkFilters();
}

function showAllOpen() {
  searchText.value = "";
  inbox.search = "";
  chooseQueue("open");
  dropLinkFilters();
}

// a chip replaces a link's ?filters=, so the address says what the list shows
function dropLinkFilters() {
  if (!route.query.filters) return;
  const { filters: _, ...query } = route.query;
  router.replace({ query });
}

function countClass(queue: Queue) {
  const n = inbox.counts[queue.key];
  if (inbox.queue === queue.key) return "bg-surface-gray-8 text-ink-base";
  if (queue.urgent && n) return "bg-danger-soft text-danger font-semibold";
  return "bg-surface-gray-2 text-ink-gray-6";
}

const listLabel = computed(() => {
  const queue = QUEUES.find((q) => q.key === inbox.queue);
  return __(
    "{0}: {1} tickets",
    queue?.label ?? __("Filtered"),
    String(inbox.rows.length)
  );
});

const EMPTY: Record<QueueKey | "filtered", string> = {
  open: __("No open tickets."),
  needsReply: __("No one is waiting for a reply."),
  overdue: __("Nothing is overdue."),
  mine: __("Nothing is assigned to you."),
  unassigned: __("Every open ticket has someone on it."),
  waiting: __("Nothing is waiting on a customer or a task."),
  resolved: __("Nothing resolved yet."),
  filtered: __("No tickets match the link's filters."),
};
const emptyText = computed(() =>
  inbox.search
    ? __("No tickets match “{0}”.", inbox.search)
    : EMPTY[inbox.queue]
);

// --- a row ---------------------------------------------------------------------------------------
function isOpenRow(row: InboxRow) {
  return String(route.params.ticketId || "") === String(row.name);
}

function who(row: InboxRow) {
  return (
    row.contact || row.last?.customer_name || row.raised_by || __("Unknown")
  );
}

function lastWho(row: InboxRow) {
  const m = row.last!;
  if (m.by === "copilot") return __("Copilot");
  if (m.by === "customer") return m.author || firstName(who(row));
  const me = getUser(userId).full_name;
  return me && me.split(" ")[0] === m.author ? __("You") : m.author;
}

function waiting(row: InboxRow) {
  return row.status_category === "Open" && row.last?.by === "customer"
    ? row.last.waiting
    : 0;
}

function assignee(row: InboxRow): string | null {
  const list: string[] = row._assign ? JSON.parse(row._assign) : [];
  return list[0] ?? null;
}

function assigneeName(row: InboxRow) {
  const id = assignee(row);
  return id ? getUser(id).full_name || id : "";
}

const slaClock = useSlaTimeLeft(() => inbox.rows);

type Signal = { label: string; tone: Tone; icon: Component };

/** At most two: what's late first, then Copilot, then whose move it is. */
function signals(row: InboxRow): Signal[] {
  const out: Signal[] = [];
  const paused =
    getStatus(row.status)?.category === "Paused" ||
    row.status_category === "Paused";
  const due = dueBadge(
    row,
    paused,
    (clock) => slaClock.workingLeft(String(row.name), clock),
    slaClock.now.value
  );
  if (due?.tone === "danger") {
    const deadline =
      due.clock === "response" ? row.response_by : row.resolution_by;
    out.push({
      label: __(
        "Overdue {0}",
        deadline ? overdueFor(deadline, slaClock.now.value) : ""
      ),
      tone: "danger",
      icon: LucideCircleAlert,
    });
  } else if (due?.tone === "warning") {
    out.push({ label: due.label, tone: "warning", icon: LucideClock });
  }
  if (row.copilot === "approve")
    out.push({
      label: __("Fix to approve"),
      tone: "info",
      icon: LucideSparkles,
    });
  else if (row.copilot === "working")
    out.push({
      label: __("Copilot working"),
      tone: "neutral",
      icon: LucideSparkles,
    });
  if (row.status === "Replied")
    out.push({
      label: __("Waiting on {0}", firstName(who(row))),
      tone: "neutral",
      icon: LucideReply,
    });
  else if (row.status === "Waiting on Task")
    out.push({
      label: __("Waiting on a task"),
      tone: "neutral",
      icon: LucideHourglass,
    });
  else if (paused)
    out.push({ label: __(row.status), tone: "neutral", icon: LucidePause });
  else if (row.status_category === "Resolved")
    out.push({
      label: __(row.status),
      tone: "success",
      icon: LucideCircleCheck,
    });
  if (!assignee(row) && row.status_category !== "Resolved")
    out.push({ label: __("Unassigned"), tone: "neutral", icon: LucideUserX });
  return out.slice(0, 2);
}

/** "now", "12m", "3h", "2d", then "12 Nov" */
function ago(at: string) {
  const minutes = dayjsLocal().diff(dayjsLocal(at), "minute");
  if (minutes < 1) return __("now");
  if (minutes < 60) return __("{0}m", [minutes]);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return __("{0}h", [hours]);
  const days = Math.floor(hours / 24);
  if (days < 7) return __("{0}d", [days]);
  return dayjs(at).format("D MMM");
}

// --- keyboard: j / k open the next or previous ticket, / searches ---------------------------
function step(by: 1 | -1) {
  if (!inbox.rows.length) return;
  const at = inbox.rows.findIndex(isOpenRow);
  const next =
    inbox.rows[
      at < 0 ? 0 : Math.min(inbox.rows.length - 1, Math.max(0, at + by))
    ];
  if (next && !isOpenRow(next))
    router.push({ name: "TicketAgent", params: { ticketId: next.name } });
}
useShortcut("j", () => step(1));
useShortcut("k", () => step(-1));
useShortcut("/", () => searchRef.value?.focus());

// the open ticket's row stays in sight
watch(
  () => route.params.ticketId,
  async () => {
    await nextTick();
    listRef.value
      ?.querySelector<HTMLElement>("[aria-current=page]")
      ?.scrollIntoView({ block: "nearest" });
  }
);

// --- loading and staying fresh --------------------------------------------------------------
// a link's ?filters= (Home's cards) picks its queue, or shows the Filtered chip
watch(
  () => route.query.filters,
  (raw) => {
    if (!takeLinkFilters(raw) && !inbox.loaded) loadInbox();
  },
  { immediate: true }
);
countQueues();

const { $socket } = globalStore();
const visibility = useDocumentVisibility();
useIntervalFn(() => {
  if (visibility.value === "visible") refreshInbox();
}, 60_000);
watch(visibility, (now) => now === "visible" && refreshInbox());
function onNewTicket() {
  refreshInbox();
}
onMounted(() => $socket.on("helpdesk:new-ticket", onNewTicket));
onBeforeUnmount(() => $socket.off("helpdesk:new-ticket", onNewTicket));

// the chosen chip stays in sight on a narrow list
watch(
  () => inbox.queue,
  async () => {
    await nextTick();
    chipsRef.value
      ?.querySelector<HTMLElement>("[aria-pressed=true]")
      ?.scrollIntoView({ block: "nearest", inline: "nearest" });
  },
  { immediate: true }
);
</script>

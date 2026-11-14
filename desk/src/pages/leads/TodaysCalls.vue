<template>
  <div class="flex flex-col gap-5">
    <TaskyState
      v-if="myCalls.error && !shown"
      class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
      error
      :icon="LucideCircleAlert"
      :title="__('Couldn\'t load today\'s calls')"
      :message="
        errorText(myCalls.error, __('Check your connection and try again.'))
      "
    >
      <Button :label="__('Try again')" @click="reload" />
    </TaskyState>

    <div
      v-else-if="!shown"
      class="flex flex-col gap-5"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-28 animate-pulse rounded-xl bg-surface-gray-3" />
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-3" />
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-3" />
    </div>

    <TaskyState
      v-else-if="!shown.available"
      class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
      :icon="LucideCloudOff"
      :title="__('Today\'s calls aren\'t available yet')"
      :message="__('The ERP site needs the latest TBO Smart.')"
    />

    <TaskyState
      v-else-if="!shown.enabled"
      class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
      :icon="LucidePhoneOff"
      :title="
        readOnly
          ? __('No call batches for them')
          : __('No call batches for you')
      "
      :message="
        shown.reason ||
        __(
          'Your department doesn\'t hand out daily call batches. Your leads are under All and Mine.'
        )
      "
    />

    <template v-else>
      <!-- title, what they call for now (a department with one thing to call has no switch), and what is overdue -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <h2 v-if="!readOnly" class="text-xl font-semibold text-ink-gray-9">
          {{ __("Today's calls") }}
        </h2>
        <CallingFor
          v-if="!readOnly && shown.focus_options?.length"
          :focus="shown.focus ?? null"
          :options="shown.focus_options"
          @changed="reload"
        />
        <TaskyBadge
          v-if="shown.overdue.length"
          class="sm:ml-auto"
          tone="danger"
          :icon="LucideAlarmClock"
          :label="__('{0} overdue', String(shown.overdue.length))"
        />
      </div>

      <!-- a failed update keeps the last queue, and says so -->
      <div
        v-if="myCalls.error"
        role="alert"
        class="flex flex-wrap items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-3"
      >
        <LucideCircleAlert
          class="size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        <p class="min-w-0 flex-1 text-p-sm text-ink-gray-8">
          {{
            __(
              "Couldn't update your calls: {0} What you see may be out of date.",
              errorText(myCalls.error, __("Check your connection."))
            )
          }}
        </p>
        <Button :label="__('Try again')" @click="reload" />
      </div>

      <!-- the batch: which slot, how long is left, how far along, and the next one -->
      <section
        :aria-labelledby="ids.batch"
        class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      >
        <div class="flex flex-wrap items-start gap-x-6 gap-y-3">
          <div class="min-w-0 flex-1">
            <template v-if="shown.batch">
              <div class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                <h3
                  :id="ids.batch"
                  class="text-base font-semibold text-ink-gray-9"
                >
                  {{ shown.batch.slot }}
                </h3>
                <span
                  class="inline-flex items-center gap-1.5 font-mono text-sm tabular-nums"
                  :class="
                    hurry ? 'font-medium text-warning' : 'text-ink-gray-7'
                  "
                  role="timer"
                >
                  <component
                    :is="hurry ? LucideAlarmClock : LucideClock"
                    class="size-4"
                    aria-hidden="true"
                  />
                  {{ timeLeftText(secondsLeft) }}
                </span>
                <span
                  v-if="shown.batch.campaign_product"
                  class="inline-flex items-center gap-1.5 text-sm text-ink-gray-7"
                >
                  <LucideBox
                    class="size-4 text-ink-gray-6"
                    aria-hidden="true"
                  />
                  {{ __("Calls for") }}: {{ shown.batch.campaign_product }}
                </span>
              </div>
              <div
                class="mt-3 h-1.5 max-w-xl overflow-hidden rounded-full"
                :class="TRACK.neutral"
                role="progressbar"
                :aria-valuemin="0"
                :aria-valuemax="counts.size"
                :aria-valuenow="counts.called"
                :aria-label="__('Calls made in this batch')"
              >
                <div
                  class="h-full rounded-full transition-[width]"
                  :class="
                    counts.called >= counts.size && counts.size
                      ? FILL.success
                      : 'bg-brand'
                  "
                  :style="{ width: `${progress}%` }"
                />
              </div>
              <p
                class="mt-2.5 flex flex-wrap items-baseline gap-x-4 gap-y-1 text-sm text-ink-gray-7"
              >
                <span
                  ><b
                    class="font-mono font-medium tabular-nums text-ink-gray-9"
                    >{{ counts.called }}</b
                  >
                  {{ __("of {0} called", String(counts.size)) }}</span
                >
                <span
                  ><b
                    class="font-mono font-medium tabular-nums text-ink-gray-9"
                    >{{ counts.connected }}</b
                  >
                  {{ __("contacted") }}</span
                >
                <span
                  ><b
                    class="font-mono font-medium tabular-nums text-ink-gray-9"
                    >{{ counts.scheduled }}</b
                  >
                  {{ __("call backs") }}</span
                >
                <span
                  v-if="counts.size && counts.called >= counts.size"
                  class="inline-flex items-center gap-1 text-success"
                >
                  <LucideCircleCheck class="size-4" aria-hidden="true" />
                  {{ __("All called") }}
                </span>
              </p>
            </template>
            <template v-else>
              <h3
                :id="ids.batch"
                class="text-base font-semibold text-ink-gray-9"
              >
                {{ __("No batch right now") }}
              </h3>
              <p class="mt-1 text-p-sm text-ink-gray-7">
                {{
                  readOnly
                    ? __("They have no batch running now.")
                    : shown.next_slot
                    ? __(
                        "Your next batch, {0}, starts at {1}.",
                        shown.next_slot.label,
                        dayjs(shown.next_slot.starts_at).format("h:mm A")
                      )
                    : __("There are no more batches today.")
                }}
              </p>
            </template>
            <p
              v-if="shown.today && shown.today.size"
              class="mt-2 font-mono text-p-xs tabular-nums text-ink-gray-6"
            >
              {{
                __(
                  "Today: {0} of {1} called, {2} contacted",
                  String(shown.today.called),
                  String(shown.today.size),
                  String(shown.today.connected)
                )
              }}
            </p>
          </div>

          <!-- the next batch, or why not yet -->
          <div
            v-if="!readOnly"
            class="flex w-full flex-col gap-2 sm:w-auto sm:max-w-xs sm:items-end"
          >
            <Button
              class="w-full sm:w-auto"
              size="md"
              :variant="shown.next_batch?.allowed ? 'solid' : 'subtle'"
              :label="__('Get next batch')"
              :disabled="!shown.next_batch?.allowed || nextBatch.loading"
              :loading="nextBatch.loading"
              :aria-describedby="
                !shown.next_batch?.allowed && shown.next_batch?.reason
                  ? ids.reason
                  : undefined
              "
              @click="getNext"
            />
            <p
              v-if="!shown.next_batch?.allowed && shown.next_batch?.reason"
              :id="ids.reason"
              class="flex items-start gap-1.5 text-p-xs text-ink-gray-6 sm:text-right"
              aria-live="polite"
            >
              <LucideInfo
                class="mt-0.5 size-3.5 shrink-0 sm:hidden"
                aria-hidden="true"
              />
              {{ shown.next_batch.reason }}
            </p>
          </div>
        </div>
      </section>

      <!-- the queue: pending first, then what was missed in its slot (kept, and still
           callable); a row opens the lead, where the call is made -->
      <section
        :aria-labelledby="ids.pending"
        class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
      >
        <h3
          :id="ids.pending"
          class="flex items-baseline justify-between border-b border-outline-gray-2 px-4 py-3 text-base font-semibold text-ink-gray-9"
        >
          {{ __("To call") }}
          <span class="font-mono text-sm tabular-nums text-ink-gray-6">{{
            queue.length
          }}</span>
        </h3>
        <ol v-if="queue.length" role="list">
          <li
            v-for="(item, i) in queue"
            :key="item.item"
            class="border-b border-outline-gray-1 last:border-b-0"
          >
            <router-link
              :to="leadRoute(item)"
              class="flex min-h-[64px] items-center gap-3 px-4 py-3 transition-colors md:px-4 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
            >
              <span
                class="w-6 shrink-0 font-mono text-sm tabular-nums text-ink-gray-6"
                >{{ i + 1 }}</span
              >
              <PersonAvatar :name="queueName(item)" size="md" neutral />
              <span class="flex min-w-0 flex-1 flex-col gap-0.5">
                <span
                  class="truncate text-[13px] font-semibold text-ink-gray-9"
                  >{{ queueName(item) }}</span
                >
                <span
                  v-if="queuePlace(item)"
                  class="truncate text-[12px] text-ink-gray-6"
                  >{{ queuePlace(item) }}</span
                >
              </span>
              <span
                v-if="item.summary.phone"
                class="hidden shrink-0 font-mono text-sm tabular-nums text-ink-gray-7 md:block"
                >{{ item.summary.phone }}</span
              >
              <TaskyBadge
                v-if="overdueItems.has(item.item)"
                tone="danger"
                :icon="LucideAlarmClock"
                :label="__('Overdue')"
              />
              <TaskyBadge
                v-else-if="item.reason"
                :tone="item.retry_at ? 'warning' : 'neutral'"
                :label="item.reason"
              />
              <LucideChevronRight
                class="size-4 shrink-0 text-ink-gray-5"
                aria-hidden="true"
              />
            </router-link>
          </li>
        </ol>
        <div
          v-else
          class="flex flex-col items-center gap-1 px-5 py-14 text-center"
        >
          <LucideCheckCheck class="size-6 text-success" aria-hidden="true" />
          <p class="text-base-medium text-ink-gray-9">
            {{
              shown.batch
                ? __("Nothing left to call in this batch")
                : __("No call waiting")
            }}
          </p>
          <p class="text-p-sm text-ink-gray-6">
            {{
              shown.scheduled.length
                ? __("Some calls come back later.")
                : readOnly
                ? __(
                    "Their next batch comes when they ask for it or the next slot opens."
                  )
                : __("Ask for the next batch when you are ready.")
            }}
          </p>
        </div>
        <p
          v-if="shown.scheduled.length"
          class="flex items-center gap-1.5 border-t border-outline-gray-2 px-5 py-3.5 text-p-sm text-ink-gray-7"
        >
          <LucideCalendarClock class="size-4 shrink-0" aria-hidden="true" />
          <span class="tabular-nums">
            {{
              __(
                "{0} come back later, the next at {1}",
                String(shown.scheduled.length),
                dayjs(shown.scheduled[0].retry_at).format("h:mm A")
              )
            }}
          </span>
        </p>
        <p
          v-if="shown.overdue.length"
          class="border-t border-outline-gray-2 px-5 py-3.5 text-p-sm text-ink-gray-7"
        >
          {{
            readOnly
              ? __(
                  "Not called in their slot. They stay here until they are called."
                )
              : __(
                  "Not called in their slot. They stay here until you call them."
                )
          }}
        </p>
      </section>
    </template>

    <!-- a watcher: what they already called today, newest first -->
    <section
      v-if="readOnly && shown?.enabled"
      :aria-labelledby="ids.called"
      class="flex flex-col gap-3"
    >
      <h2
        :id="ids.called"
        class="flex items-center gap-2 text-base font-semibold text-ink-gray-9"
      >
        <LucidePhoneOutgoing
          class="size-4 text-ink-gray-6"
          aria-hidden="true"
        />
        {{ __("Called today") }}
        <span class="font-mono tabular-nums text-ink-gray-6">{{
          shown.called?.length ?? 0
        }}</span>
      </h2>
      <p
        v-if="!shown.called?.length"
        class="rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-14 text-center text-p-sm text-ink-gray-6"
      >
        {{ __("No calls made yet today.") }}
      </p>
      <ul
        v-else
        role="list"
        class="divide-y divide-outline-gray-1 overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base"
        :aria-label="__('Called today')"
      >
        <li
          v-for="item in shown.called"
          :key="item.item"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3"
        >
          <span class="min-w-0 flex-1">
            <span
              class="block truncate text-[13px] font-semibold text-ink-gray-9"
            >
              {{ item.summary.lead_name || item.summary.name || item.lead }}
            </span>
            <span class="block truncate text-p-sm text-ink-gray-6">
              {{
                [item.summary.company_name, item.summary.phone]
                  .filter(Boolean)
                  .join(" · ")
              }}
            </span>
            <span
              v-if="item.note"
              class="block line-clamp-2 text-p-sm text-ink-gray-7"
              >{{ item.note }}</span
            >
          </span>
          <TaskyBadge
            :tone="OUTCOME_LOOK[item.outcome]?.tone"
            :icon="OUTCOME_LOOK[item.outcome]?.icon"
            :label="outcomeLabel(item.outcome)"
          />
          <span
            v-if="item.called_at"
            class="w-16 text-right font-mono text-sm tabular-nums text-ink-gray-6"
            >{{ dayjs(item.called_at).format("h:mm A") }}</span
          >
        </li>
      </ul>
    </section>
  </div>
</template>

<script setup lang="ts">
import PersonAvatar from "@/components/PersonAvatar.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { FILL, TRACK } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDocumentVisibility, useIntervalFn, useNow } from "@vueuse/core";
import { Button, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBox from "~icons/lucide/box";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideInfo from "~icons/lucide/info";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucidePhoneOutgoing from "~icons/lucide/phone-outgoing";
import CallingFor from "./CallingFor.vue";
import {
  OUTCOME_LOOK,
  OUTCOMES,
  timeLeftText,
  useMemberCalls,
  useMyCalls,
  useNextBatch,
  type CallCounts,
  type CallOutcome,
  type MyCalls,
  type QueueCall,
} from "./callBatches";
import { queueChanged } from "./pendingCalls";

const ids = {
  batch: `calls-batch-${useId()}`,
  pending: `calls-pending-${useId()}`,
  reason: `calls-reason-${useId()}`,
  called: `calls-called-${useId()}`,
};

const props = defineProps<{
  /** someone else's calls (their email), watched read-only from Assign leads */
  member?: string;
}>();
const readOnly = computed(() => !!props.member);
const outcomeLabel = (value: CallOutcome) =>
  OUTCOMES.find((o) => o.value === value)?.label ?? value;
// under this many seconds left the clock turns to a warning
const HURRY_SECONDS = 15 * 60;
// a watcher wants it live; the caller's own results update it through queueChanged
const REFRESH_MS = props.member ? 15_000 : 60_000;

const myCalls = props.member ? useMemberCalls(props.member) : useMyCalls();

// what the person sees: the last queue read, kept when a later read fails
const shown = ref<MyCalls>();
const fetchedAt = ref(Date.now());

watch(
  () => myCalls.data as MyCalls | undefined,
  (data) => {
    if (!data) return;
    shown.value = data;
    fetchedAt.value = Date.now();
  },
  { immediate: true }
);
myCalls.fetch();

function reload() {
  myCalls.reload();
}
defineExpose({ reload });
watch(queueChanged, reload);

// calls made another way (MyOperator, the phone's log) count on the ERP site: ask again
// every minute and whenever the tab comes back
useIntervalFn(() => {
  if (!document.hidden) reload();
}, REFRESH_MS);
const visibility = useDocumentVisibility();
watch(visibility, (state) => {
  if (state === "visible") reload();
});

const now = useNow({ interval: 1000 });
const secondsLeft = computed(() => {
  const left = shown.value?.batch?.seconds_left ?? 0;
  return Math.max(
    left - Math.floor((now.value.getTime() - fetchedAt.value) / 1000),
    0
  );
});
const hurry = computed(
  () => secondsLeft.value > 0 && secondsLeft.value <= HURRY_SECONDS
);
// when the slot ends its calls turn overdue: read the queue again
watch(secondsLeft, (left, before) => {
  if (before > 0 && left === 0 && shown.value?.batch) setTimeout(reload, 2000);
});

const counts = computed<CallCounts>(
  () =>
    shown.value?.counts ?? {
      size: 0,
      called: 0,
      connected: 0,
      pending: 0,
      scheduled: 0,
      overdue: 0,
    }
);
const progress = computed(() =>
  counts.value.size
    ? Math.min(Math.round((counts.value.called / counts.value.size) * 100), 100)
    : 0
);

// the queue: what is to call now, then what was missed in its slot
const queue = computed(() =>
  shown.value ? [...shown.value.pending, ...shown.value.overdue] : []
);
const overdueItems = computed(
  () => new Set((shown.value?.overdue ?? []).map((c) => c.item))
);
const queueName = (c: QueueCall) =>
  c.summary.lead_name || c.summary.name || c.lead;
const queuePlace = (c: QueueCall) =>
  [c.summary.company_name, c.summary.district].filter(Boolean).join(" · ");

/** The lead's page, where the call is made; the batch item goes along so the result the
 * call sheet asks for counts in this batch (a watcher only looks). */
const leadRoute = (c: QueueCall) => ({
  name: "Lead",
  params: { leadId: c.lead },
  query: readOnly.value ? undefined : { item: c.item },
});

// ---------- the next batch ----------

const nextBatch = useNextBatch();

function getNext() {
  nextBatch.submit(
    {},
    {
      onSuccess(result: { created: boolean; reason?: string }) {
        if (!result.created)
          toast.info(result.reason || __("There is no next batch yet."));
        reload();
      },
    }
  );
}
</script>

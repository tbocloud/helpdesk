<template>
  <div class="flex flex-col gap-4">
    <TaskyState
      v-if="myCalls.error && !shown"
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
      class="flex flex-col gap-3"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-24 animate-pulse rounded-xl bg-surface-gray-2" />
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-2" />
      <div class="h-40 animate-pulse rounded-xl bg-surface-gray-2" />
    </div>

    <TaskyState
      v-else-if="!shown.available"
      :icon="LucideCloudOff"
      :title="__('Today\'s calls aren\'t available yet')"
      :message="__('The ERP site needs the latest TBO Smart.')"
    />

    <TaskyState
      v-else-if="!shown.enabled"
      :icon="LucidePhoneOff"
      :title="__('No call batches for you')"
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
        <h2 class="text-xl font-semibold text-ink-gray-9">
          {{ __("Today's calls") }}
        </h2>
        <CallingFor
          v-if="shown.focus_options?.length"
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

      <div
        class="grid items-start gap-4 lg:grid-cols-[minmax(0,26rem)_minmax(0,1fr)] lg:gap-6"
      >
        <!-- the batch: which slot, how long is left, how far along -->
        <section
          :aria-labelledby="ids.batch"
          class="rounded-xl border border-outline-gray-2 bg-surface-base lg:col-start-1 lg:row-start-1"
        >
          <div class="p-4">
            <template v-if="shown.batch">
              <div class="flex flex-wrap items-baseline gap-x-2">
                <h3 :id="ids.batch" class="text-base-medium text-ink-gray-9">
                  {{ shown.batch.slot }}
                </h3>
                <span
                  class="ml-auto inline-flex items-center gap-1.5 font-mono text-sm tabular-nums"
                  :class="
                    hurry ? 'font-medium text-warning' : 'text-ink-gray-8'
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
              </div>
              <!-- the product the next batches are for, when a manager set one -->
              <p
                v-if="shown.batch.campaign_product"
                class="mt-1 inline-flex items-center gap-1.5 text-sm text-ink-gray-7"
              >
                <LucideBox class="size-4 text-ink-gray-6" aria-hidden="true" />
                {{ __("Calls for") }}: {{ shown.batch.campaign_product }}
              </p>
              <div
                class="mt-3 h-1.5 overflow-hidden rounded-full"
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
              <h3 :id="ids.batch" class="text-base-medium text-ink-gray-9">
                {{ __("No batch right now") }}
              </h3>
              <p class="mt-1 text-p-sm text-ink-gray-7">
                {{
                  shown.next_slot
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
              class="mt-2.5 font-mono text-p-xs tabular-nums text-ink-gray-6"
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
        </section>

        <!-- the call to make now -->
        <div class="lg:col-start-2 lg:row-span-3 lg:row-start-1">
          <CallRow
            v-if="current"
            :key="current.item"
            :call="current"
            :position="
              __(
                'Call {0} of {1}',
                String(currentPosition),
                String(queue.length)
              )
            "
            :overdue="overdueItems.has(current.item)"
            :can-call="!!shown.can_call"
            :dialing="dialing === current.lead"
            @dial="dial"
            @dialed="dialed"
            @outcome="answer"
          />
          <div
            v-else
            class="flex flex-col items-center gap-1 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-12 text-center"
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
                  ? __("Some calls come back later, listed below.")
                  : __("Ask for the next batch when you are ready.")
              }}
            </p>
          </div>
        </div>

        <!-- the queue: pending first, then what was missed in its slot (kept, and still callable) -->
        <section
          :aria-labelledby="ids.pending"
          class="overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-base lg:col-start-1 lg:row-start-2"
        >
          <h3
            :id="ids.pending"
            class="flex items-baseline justify-between border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
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
              <button
                type="button"
                class="relative flex w-full items-center gap-3 px-4 py-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                :class="
                  item.item === current?.item
                    ? 'bg-brand-soft before:absolute before:inset-y-0 before:left-0 before:w-[3px] before:bg-brand'
                    : 'hover:bg-surface-gray-1'
                "
                :aria-current="item.item === current?.item ? 'true' : undefined"
                @click="pickedItem = item.item"
              >
                <span
                  class="w-5 shrink-0 font-mono text-sm tabular-nums text-ink-gray-6"
                  >{{ i + 1 }}</span
                >
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="truncate text-base-medium text-ink-gray-9">{{
                    queueName(item)
                  }}</span>
                  <span class="truncate text-sm text-ink-gray-6">{{
                    queuePlace(item)
                  }}</span>
                </span>
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
              </button>
            </li>
          </ol>
          <p v-else class="px-4 py-6 text-center text-p-sm text-ink-gray-6">
            {{ __("The queue is empty.") }}
          </p>
          <p
            v-if="shown.scheduled.length"
            class="flex items-center gap-1.5 border-t border-outline-gray-1 px-4 py-3 text-p-sm text-ink-gray-7"
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
            class="border-t border-outline-gray-1 px-4 py-3 text-p-sm text-ink-gray-7"
          >
            {{
              __(
                "Not called in their slot. They stay here until you call them."
              )
            }}
          </p>
        </section>

        <!-- the next batch, or why not yet -->
        <div class="flex flex-col gap-2 lg:col-start-1 lg:row-start-3">
          <Button
            class="w-full sm:w-auto sm:self-start"
            size="lg"
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
            class="flex items-start gap-1.5 text-p-sm text-ink-gray-7"
            aria-live="polite"
          >
            <LucideInfo class="mt-0.5 size-4 shrink-0" aria-hidden="true" />
            {{ shown.next_batch.reason }}
          </p>
        </div>
      </div>
    </template>

    <CallOutcomeDialog
      v-model:open="showOutcome"
      :mode="flow"
      :call="flowCall"
      :stages="options?.stages ?? []"
      :start-note="flowNote"
      @answer="saveFlow"
    />
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { FILL, TRACK } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDocumentVisibility, useIntervalFn, useNow } from "@vueuse/core";
import { Button, call, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideBox from "~icons/lucide/box";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideInfo from "~icons/lucide/info";
import LucidePhoneOff from "~icons/lucide/phone-off";
import CallingFor from "./CallingFor.vue";
import CallOutcomeDialog, { type OutcomeAnswer } from "./CallOutcomeDialog.vue";
import CallRow from "./CallRow.vue";
import {
  timeLeftText,
  useMyCalls,
  useNextBatch,
  useRecordOutcome,
  withOutcome,
  type CallCounts,
  type CallOutcome,
  type MyCalls,
  type QueueCall,
} from "./callBatches";
import { loadPendingCalls, queueChanged, startCall } from "./pendingCalls";
import {
  leadOptions,
  loadLeadOptions,
  useClickToCall,
  type LeadOptions,
} from "./leads";

const ids = {
  batch: `calls-batch-${useId()}`,
  pending: `calls-pending-${useId()}`,
  reason: `calls-reason-${useId()}`,
};
// under this many seconds left the clock turns to a warning
const HURRY_SECONDS = 15 * 60;
const REFRESH_MS = 60_000;

const myCalls = useMyCalls();
loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);

// what the person sees: the server's queue, changed at once by their own answers
const shown = ref<MyCalls>();
const fetchedAt = ref(Date.now());
let inflight = 0;

watch(
  () => myCalls.data as MyCalls | undefined,
  (data) => {
    if (!data || inflight) return;
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
  if (!document.hidden && !inflight) reload();
}, REFRESH_MS);
const visibility = useDocumentVisibility();
watch(visibility, (state) => {
  if (state === "visible" && !inflight) reload();
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

// the queue: what is to call now, then what was missed in its slot; one is the call on screen
const queue = computed(() =>
  shown.value ? [...shown.value.pending, ...shown.value.overdue] : []
);
const overdueItems = computed(
  () => new Set((shown.value?.overdue ?? []).map((c) => c.item))
);
const pickedItem = ref("");
const current = computed(
  () => queue.value.find((c) => c.item === pickedItem.value) ?? queue.value[0]
);
const currentPosition = computed(() =>
  current.value ? queue.value.indexOf(current.value) + 1 : 0
);
const queueName = (c: QueueCall) =>
  c.summary.lead_name || c.summary.name || c.lead;
const queuePlace = (c: QueueCall) =>
  [c.summary.company_name, c.summary.district].filter(Boolean).join(" · ");

// ---------- calling ----------

const clickToCall = useClickToCall();
const dialing = computed(() =>
  clickToCall.loading ? (clickToCall.params?.name as string) : ""
);

// the number last dialled for each call, when it was not the main one: the result names it
const dialledNumbers = new Map<string, string>();

/** MyOperator rings the person's phone, then the lead; without it the row's tel: link dials.
 * `number` is one of the lead's other numbers (none: the main one). */
function dial(item: QueueCall, number?: string) {
  clickToCall.submit({ name: item.lead, number: number || null });
  remember(item, "myoperator", number);
}

function dialed(item: QueueCall, number?: string) {
  remember(item, "phone", number);
}

/** A call placed: it waits for its result, and the result sheet follows. */
function remember(
  item: QueueCall,
  via: "phone" | "myoperator",
  number?: string
) {
  if (number) dialledNumbers.set(item.item, number);
  else dialledNumbers.delete(item.item);
  startCall({
    lead: item.lead,
    lead_name: item.summary.lead_name || item.summary.name,
    phone: number || item.summary.phone,
    number: number || null,
    item: item.item,
    via,
  });
}

// ---------- outcomes ----------

const recording = useRecordOutcome();
const showOutcome = ref(false);
const flow = ref<"Connected" | "Call back" | "Not interested" | null>(null);
const flowCall = ref<QueueCall | null>(null);
const flowNote = ref("");

/** A button: the plain answers are saved at once, with the card's note; the others ask for more first. */
function answer(item: QueueCall, outcome: CallOutcome, note = "") {
  if (
    outcome === "Connected" ||
    outcome === "Call back" ||
    outcome === "Not interested"
  ) {
    flow.value = outcome;
    flowCall.value = item;
    flowNote.value = note;
    showOutcome.value = true;
    return;
  }
  save(item, { outcome, note, callback_at: null, stage: null });
}

function saveFlow(answerValue: OutcomeAnswer) {
  if (flowCall.value) save(flowCall.value, answerValue);
}

/** The counter goes down at once; the ERP site's answer settles it, and a refusal puts the
 * call back with the reason. Low risk: a call is logged, nothing is paid or deleted. */
function save(item: QueueCall, value: OutcomeAnswer) {
  if (!shown.value) return;
  const before = shown.value;
  shown.value = withOutcome(before, item);
  inflight++;
  recording.submit(
    {
      batch_item: item.item,
      lead: item.lead,
      outcome: value.outcome,
      note: value.note || null,
      callback_at: value.callback_at,
      number: dialledNumbers.get(item.item) ?? null,
    },
    {
      onSuccess() {
        inflight--;
        if (value.stage) moveStage(item, value);
        settle();
      },
      onError(e: unknown) {
        inflight--;
        if (!inflight) shown.value = before;
        toast.error(errorText(e, __("Couldn't save the call. Try again.")));
        settle();
      },
    }
  );
}

function moveStage(item: QueueCall, value: OutcomeAnswer) {
  call("helpdesk.api.leads.set_stage", {
    name: item.lead,
    stage: value.stage,
    note: value.note || null,
  }).catch((e: unknown) =>
    toast.error(
      __(
        "Call saved, but the lead didn't move: {0}",
        errorText(e, __("Try again from the lead."))
      )
    )
  );
}

/** Once nothing is in flight the queue is read again, which also brings a retry or call back. */
function settle() {
  loadPendingCalls();
  if (!inflight) reload();
}

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

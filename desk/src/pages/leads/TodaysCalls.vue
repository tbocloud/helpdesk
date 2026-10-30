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

      <!-- the batch: which slot, how long is left, how far along -->
      <section
        :aria-labelledby="ids.batch"
        class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
      >
        <template v-if="shown.batch">
          <div class="flex flex-wrap items-baseline justify-between gap-x-4">
            <h2 :id="ids.batch" class="text-lg-medium text-ink-gray-9">
              {{ shown.batch.slot }}
            </h2>
            <span
              class="inline-flex items-center gap-1.5 text-sm tabular-nums"
              :class="hurry ? 'font-medium text-warning' : 'text-ink-gray-7'"
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
          <div class="mt-3 flex items-baseline justify-between gap-3">
            <p class="font-mono text-base-medium tabular-nums text-ink-gray-9">
              {{
                __(
                  "{0} / {1} called",
                  String(counts.called),
                  String(counts.size)
                )
              }}
            </p>
            <p
              v-if="counts.size && counts.called >= counts.size"
              class="inline-flex items-center gap-1 text-sm text-success"
            >
              <LucideCircleCheck class="size-4" aria-hidden="true" />
              {{ __("All called") }}
            </p>
          </div>
          <div
            class="mt-2 h-2 overflow-hidden rounded-full"
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
                  : FILL.neutral
              "
              :style="{ width: `${progress}%` }"
            />
          </div>
        </template>
        <template v-else>
          <h2 :id="ids.batch" class="text-lg-medium text-ink-gray-9">
            {{ __("No batch right now") }}
          </h2>
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
          class="mt-3 font-mono text-p-xs tabular-nums text-ink-gray-6"
        >
          {{
            __(
              "Today: {0} of {1} called, {2} connected",
              String(shown.today.called),
              String(shown.today.size),
              String(shown.today.connected)
            )
          }}
        </p>
      </section>

      <!-- to call now -->
      <section :aria-labelledby="ids.pending" class="flex flex-col gap-2">
        <h2 :id="ids.pending" class="sr-only">{{ __("To call") }}</h2>
        <ul
          v-if="shown.pending.length"
          role="list"
          class="flex flex-col gap-3"
          :aria-label="__('To call')"
        >
          <CallRow
            v-for="item in shown.pending"
            :key="item.item"
            :call="item"
            :can-call="!!shown.can_call"
            :dialing="dialing === item.lead"
            @dial="dial"
            @outcome="answer"
          />
        </ul>
        <div
          v-else-if="shown.batch"
          class="flex flex-col items-center gap-1 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-8 text-center"
        >
          <LucideCheckCheck class="size-6 text-success" aria-hidden="true" />
          <p class="text-base-medium text-ink-gray-9">
            {{ __("Nothing left to call in this batch") }}
          </p>
          <p class="text-p-sm text-ink-gray-6">
            {{
              shown.scheduled.length
                ? __("Some calls come back later, listed below.")
                : __("Ask for the next batch below when you are ready.")
            }}
          </p>
        </div>

        <p
          v-if="shown.scheduled.length"
          class="flex items-center gap-1.5 px-1 text-p-sm text-ink-gray-7"
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
      </section>

      <!-- the next batch, or why not yet -->
      <div class="flex flex-col gap-2">
        <Button
          class="w-full sm:w-auto sm:self-start"
          size="lg"
          :variant="shown.next_batch?.allowed ? 'solid' : 'subtle'"
          :label="__('Get next batch')"
          :disabled="!shown.next_batch?.allowed || nextBatch.loading"
          :loading="nextBatch.loading"
          :aria-describedby="ids.reason"
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

      <!-- missed in their slot: kept, and still callable -->
      <section
        v-if="shown.overdue.length"
        :aria-labelledby="ids.overdue"
        class="flex flex-col gap-2"
      >
        <h2
          :id="ids.overdue"
          class="flex items-center gap-2 text-base-medium text-danger"
        >
          <LucideAlarmClock class="size-4" aria-hidden="true" />
          {{ __("Overdue") }}
          <span class="font-mono tabular-nums">{{ shown.overdue.length }}</span>
        </h2>
        <p class="text-p-sm text-ink-gray-7">
          {{
            __("Not called in their slot. They stay here until you call them.")
          }}
        </p>
        <ul role="list" class="flex flex-col gap-3" :aria-label="__('Overdue')">
          <CallRow
            v-for="item in shown.overdue"
            :key="item.item"
            :call="item"
            overdue
            :can-call="!!shown.can_call"
            :dialing="dialing === item.lead"
            @dial="dial"
            @outcome="answer"
          />
        </ul>
      </section>
    </template>

    <CallOutcomeDialog
      v-model:open="showOutcome"
      :mode="flow"
      :call="flowCall"
      :stages="options?.stages ?? []"
      @answer="saveFlow"
    />
  </div>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { FILL, TRACK } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { useDocumentVisibility, useIntervalFn, useNow } from "@vueuse/core";
import { Button, call, dayjs, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCheckCheck from "~icons/lucide/check-check";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideClock from "~icons/lucide/clock";
import LucideCloudOff from "~icons/lucide/cloud-off";
import LucideInfo from "~icons/lucide/info";
import LucidePhoneOff from "~icons/lucide/phone-off";
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
import {
  leadOptions,
  loadLeadOptions,
  useClickToCall,
  type LeadOptions,
} from "./leads";

const ids = {
  batch: `calls-batch-${useId()}`,
  pending: `calls-pending-${useId()}`,
  overdue: `calls-overdue-${useId()}`,
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

// ---------- calling ----------

const clickToCall = useClickToCall();
const dialing = computed(() =>
  clickToCall.loading ? (clickToCall.params?.name as string) : ""
);

/** MyOperator rings the person's phone, then the lead; without it the row's tel: link dials. */
function dial(lead: string) {
  clickToCall.submit({ name: lead });
}

// ---------- outcomes ----------

const recording = useRecordOutcome();
const showOutcome = ref(false);
const flow = ref<"Connected" | "Call back" | "Not interested" | null>(null);
const flowCall = ref<QueueCall | null>(null);

/** A chip: the plain answers are saved at once; the others ask for more first. */
function answer(item: QueueCall, outcome: CallOutcome) {
  if (
    outcome === "Connected" ||
    outcome === "Call back" ||
    outcome === "Not interested"
  ) {
    flow.value = outcome;
    flowCall.value = item;
    showOutcome.value = true;
    return;
  }
  save(item, { outcome, note: "", callback_at: null, stage: null });
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
      outcome: value.outcome,
      note: value.note || null,
      callback_at: value.callback_at,
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

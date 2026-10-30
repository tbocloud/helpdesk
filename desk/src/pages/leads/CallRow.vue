<template>
  <li
    class="flex flex-col gap-3 rounded-xl border bg-surface-base p-4"
    :class="overdue ? 'border-danger' : 'border-outline-gray-2'"
  >
    <div class="flex min-w-0 flex-col gap-1">
      <div class="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
        <router-link
          :to="{ name: 'Lead', params: { leadId: call.lead } }"
          class="truncate rounded text-base-medium text-ink-gray-9 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :title="name"
          >{{ name }}</router-link
        >
        <TaskyBadge
          v-if="overdue"
          tone="danger"
          :icon="LucideAlarmClock"
          :label="__('Overdue')"
        />
        <TaskyBadge
          v-else-if="call.reason"
          :icon="LucideInfo"
          :label="call.reason"
        />
        <TaskyBadge
          v-if="call.summary.temperature === 'Hot'"
          tone="warning"
          :icon="LucideFlame"
          :label="__('Hot')"
        />
      </div>
      <p v-if="meta" class="truncate text-p-sm text-ink-gray-7" :title="meta">
        {{ meta }}
      </p>
      <p
        v-if="call.summary.phone"
        class="font-mono text-sm tabular-nums text-ink-gray-8"
      >
        {{ call.summary.phone }}
      </p>
      <p
        v-if="call.summary.last_note"
        class="line-clamp-2 text-p-sm text-ink-gray-6"
      >
        <span class="font-medium">{{ __("Last note") }}:</span>
        {{ call.summary.last_note }}
      </p>
      <p
        v-if="call.summary.next_step"
        class="line-clamp-2 flex items-start gap-1 text-p-sm text-ink-gray-7"
      >
        <LucideSparkles
          class="mt-0.5 size-3.5 shrink-0 text-ink-gray-5"
          aria-hidden="true"
        />
        <span>
          <span class="sr-only">{{ __("AI suggests") }}: </span
          >{{ call.summary.next_step }}
        </span>
      </p>
    </div>

    <!-- the one big action: MyOperator rings the person's phone, else the phone dials -->
    <button
      v-if="canCall"
      type="button"
      :class="CALL_BUTTON"
      :disabled="dialing"
      :aria-label="__('Call {0}', name)"
      @click="emit('dial', call.lead)"
    >
      <LucideLoaderCircle
        v-if="dialing"
        class="size-5 animate-spin"
        aria-hidden="true"
      />
      <LucidePhone v-else class="size-5" aria-hidden="true" />
      {{ __("Call") }}
    </button>
    <a
      v-else-if="dialable"
      :href="`tel:${dialable}`"
      :class="CALL_BUTTON"
      :aria-label="__('Call {0}', name)"
    >
      <LucidePhone class="size-5" aria-hidden="true" />
      {{ __("Call") }}
    </a>

    <div
      class="flex flex-wrap gap-2"
      role="group"
      :aria-label="__('How did the call with {0} go?', name)"
    >
      <button
        v-for="chip in CHIPS"
        :key="chip.value"
        type="button"
        class="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-outline-gray-2 bg-surface-base px-3 text-sm text-ink-gray-8 transition-colors hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        @click="emit('outcome', call, chip.value)"
      >
        <component :is="chip.icon" class="size-4" aria-hidden="true" />
        {{ chip.label }}
      </button>
    </div>
  </li>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { computed } from "vue";
import LucideAlarmClock from "~icons/lucide/alarm-clock";
import LucideCalendarClock from "~icons/lucide/calendar-clock";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideFlame from "~icons/lucide/flame";
import LucideInfo from "~icons/lucide/info";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneMissed from "~icons/lucide/phone-missed";
import LucidePhoneOff from "~icons/lucide/phone-off";
import LucideSparkles from "~icons/lucide/sparkles";
import LucideThumbsDown from "~icons/lucide/thumbs-down";
import LucideX from "~icons/lucide/x";
import {
  dialNumber,
  OUTCOMES,
  type CallOutcome,
  type QueueCall,
} from "./callBatches";

const props = defineProps<{
  call: QueueCall;
  canCall: boolean;
  dialing?: boolean;
  overdue?: boolean;
}>();
const emit = defineEmits<{
  (e: "dial", lead: string): void;
  (e: "outcome", call: QueueCall, outcome: CallOutcome): void;
}>();

// the primary button, as a frappe-ui solid one: at least 48px tall for a thumb
const CALL_BUTTON =
  "inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 text-base-medium text-brand-on transition-colors hover:bg-brand-hover focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight focus-visible:ring-offset-2 disabled:opacity-60 sm:w-48";

const ICONS = {
  Connected: LucideCircleCheck,
  "Not answered": LucidePhoneMissed,
  Busy: LucidePhoneOff,
  "Call back": LucideCalendarClock,
  "Not interested": LucideThumbsDown,
  "Wrong number": LucideX,
};
const CHIPS = OUTCOMES.map((o) => ({ ...o, icon: ICONS[o.value] }));

const name = computed(
  () =>
    props.call.summary.lead_name || props.call.summary.name || props.call.lead
);
const meta = computed(() =>
  [
    props.call.summary.company_name,
    props.call.summary.industry,
    props.call.summary.district,
  ]
    .filter(Boolean)
    .join(" · ")
);
const dialable = computed(() => dialNumber(props.call.summary.phone));
</script>

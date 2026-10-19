<template>
  <div class="flex min-w-0 flex-col gap-2">
    <p class="flex flex-wrap items-center gap-x-2 gap-y-1">
      <span class="sr-only">{{ __("Call") }}: </span>
      <span
        class="text-base-medium"
        :class="missed ? 'text-danger' : 'text-ink-gray-9'"
        >{{ title }}</span
      >
      <span
        v-if="!missed && entry.duration"
        class="font-mono text-sm tabular-nums text-ink-gray-6"
        :title="__('Talk time')"
      >
        <span class="sr-only">{{ __("Talk time") }}: </span
        >{{ callLength(entry.duration) }}
      </span>
    </p>

    <audio
      v-if="entry.recording"
      class="h-9 w-full max-w-md"
      controls
      preload="none"
      :src="recordingUrl"
      :aria-label="__('Recording of this call')"
    />

    <details
      v-if="entry.summary"
      class="group rounded-lg border border-outline-gray-2 bg-surface-gray-1"
    >
      <summary
        class="flex min-h-[44px] cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight [&::-webkit-details-marker]:hidden"
      >
        <LucideChevronRight
          class="size-4 shrink-0 text-ink-gray-5 transition-transform group-open:rotate-90"
          aria-hidden="true"
        />
        <LucideBot class="size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
        <span class="min-w-0 flex-1 truncate">{{ entry.summary.text }}</span>
        <span class="shrink-0 text-xs text-ink-gray-5">{{ __("TBO AI") }}</span>
      </summary>
      <dl class="flex flex-col gap-2 border-t border-outline-gray-2 px-3 py-3">
        <div class="flex flex-col gap-0.5">
          <dt class="text-xs text-ink-gray-5">
            {{ __("What was discussed") }}
          </dt>
          <dd class="text-p-sm text-ink-gray-8">{{ entry.summary.text }}</dd>
        </div>
        <div v-if="entry.summary.interest" class="flex flex-col gap-0.5">
          <dt class="text-xs text-ink-gray-5">{{ __("Interested in") }}</dt>
          <dd class="text-p-sm text-ink-gray-8">
            {{ entry.summary.interest }}
          </dd>
        </div>
        <div v-if="entry.summary.intent" class="flex flex-col gap-0.5">
          <dt class="text-xs text-ink-gray-5">{{ __("Buying intent") }}</dt>
          <dd class="text-p-sm text-ink-gray-8">
            {{ INTENT_LABELS[entry.summary.intent] || entry.summary.intent }}
          </dd>
        </div>
        <div
          v-if="entry.summary.objections?.length"
          class="flex flex-col gap-0.5"
        >
          <dt class="text-xs text-ink-gray-5">{{ __("Concerns") }}</dt>
          <dd class="text-p-sm text-ink-gray-8">
            <ul role="list" class="list-inside list-disc">
              <li v-for="item in entry.summary.objections" :key="item">
                {{ item }}
              </li>
            </ul>
          </dd>
        </div>
        <div v-if="entry.summary.next_step" class="flex flex-col gap-0.5">
          <dt class="text-xs text-ink-gray-5">{{ __("Next step") }}</dt>
          <dd class="text-p-sm text-ink-gray-8">
            {{ entry.summary.next_step.what }}
            <span class="text-ink-gray-6">
              ·
              <time :datetime="entry.summary.next_step.due">{{
                dayjs(entry.summary.next_step.due).format("ddd, D MMM")
              }}</time>
            </span>
          </dd>
        </div>
        <div v-if="entry.summary.language" class="flex flex-col gap-0.5">
          <dt class="text-xs text-ink-gray-5">{{ __("Spoken in") }}</dt>
          <dd class="text-p-sm text-ink-gray-8">
            {{ entry.summary.language }}
          </dd>
        </div>
      </dl>
    </details>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import LucideBot from "~icons/lucide/bot";
import LucideChevronRight from "~icons/lucide/chevron-right";
import { callLength, type LeadTimelineEntry } from "./leads";

const props = defineProps<{ entry: LeadTimelineEntry }>();

const INTENT_LABELS: Record<string, string> = {
  High: __("High"),
  Medium: __("Medium"),
  Low: __("Low"),
  None: __("None yet"),
};

// only an explicit missed status is a missed call; an unknown one stays neutral
const missed = computed(() => props.entry.status === "missed");

const title = computed(() => {
  const incoming = props.entry.direction === "incoming";
  if (props.entry.status === "voicemail") return __("Voicemail");
  if (missed.value) return incoming ? __("Missed call") : __("Unanswered call");
  if (!props.entry.direction) return __("Call");
  return incoming ? __("Incoming call") : __("Outgoing call");
});

// the hub streams it from the ERP site, which checks the person may read the lead
const recordingUrl = computed(
  () =>
    `/api/method/helpdesk.api.leads.call_recording?call=${encodeURIComponent(
      props.entry.recording || ""
    )}`
);
</script>

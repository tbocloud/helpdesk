<template>
  <details
    v-if="calls.length"
    class="group rounded-lg border border-outline-gray-2"
  >
    <summary
      class="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm-medium text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight [&::-webkit-details-marker]:hidden"
    >
      <LucideChevronRight
        class="size-4 shrink-0 text-ink-gray-5 transition-transform group-open:rotate-90"
        aria-hidden="true"
      />
      {{ __("This lead's recent calls") }}
      <span class="font-mono tabular-nums text-ink-gray-6">{{
        calls.length
      }}</span>
    </summary>
    <ul
      role="list"
      class="flex flex-col divide-y divide-outline-gray-2 border-t border-outline-gray-2"
    >
      <li
        v-for="entry in calls"
        :key="entry.call || entry.at"
        class="flex flex-col gap-2 px-3 py-3"
      >
        <p
          class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 text-sm text-ink-gray-6"
        >
          <span
            :class="callMeta(entry).missed ? 'text-danger' : 'text-ink-gray-9'"
            >{{ callMeta(entry).kind }}</span
          >
          <template v-if="callMeta(entry).status">
            <span aria-hidden="true">·</span>
            <span :class="callMeta(entry).missed ? 'text-danger' : ''">{{
              callMeta(entry).status
            }}</span>
          </template>
          <template v-if="callMeta(entry).duration">
            <span aria-hidden="true">·</span>
            <span class="font-mono tabular-nums">{{
              callMeta(entry).duration
            }}</span>
          </template>
        </p>
        <time
          v-if="entry.at"
          class="text-xs text-ink-gray-6"
          :datetime="entry.at"
          >{{ dayjs(entry.at).format("D MMM, h:mm A") }}</time
        >
        <CallRecording
          v-if="entry.recording"
          lazy
          :src="recordingUrl(entry.recording)"
        />
        <p
          v-else-if="entry.recording_state === 'pending'"
          class="text-p-sm text-ink-gray-6"
        >
          {{ __("Recording is being saved…") }}
        </p>
      </li>
    </ul>
  </details>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import LucideChevronRight from "~icons/lucide/chevron-right";
import CallRecording from "./CallRecording.vue";
import { callMeta, recordingUrl, type LeadTimelineEntry } from "./leads";

defineProps<{ calls: LeadTimelineEntry[] }>();
</script>

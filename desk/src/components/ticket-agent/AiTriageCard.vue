<template>
  <PanelSection
    v-if="status"
    :title="__('Triage')"
    :icon="LucideScanSearch"
    :level="3"
  >
    <div aria-live="polite">
      <p
        v-if="status === 'Pending'"
        role="status"
        class="flex flex-wrap items-center gap-2 text-sm text-ink-gray-6"
      >
        <LucideLoaderCircle
          class="size-4 shrink-0 animate-spin"
          aria-hidden="true"
        />
        {{ __("Reading the ticket…") }}
        <button
          type="button"
          class="rounded font-medium text-ink-gray-8 underline underline-offset-2 hover:text-ink-gray-9"
          @click="ticket.reload()"
        >
          {{ __("Check again") }}
        </button>
      </p>

      <p
        v-else-if="status === 'Failed'"
        class="flex items-center gap-1.5 text-sm text-danger"
      >
        <LucideCircleAlert class="size-4 shrink-0" aria-hidden="true" />
        {{ __("Triage didn't finish for this ticket") }}
      </p>

      <template v-else>
        <div
          v-if="summary"
          class="triage-summary text-p-sm text-ink-gray-8"
          v-html="summary"
        />
        <dl v-if="facts.length" class="mt-2.5 flex flex-col gap-1">
          <div
            v-for="fact in facts"
            :key="fact.label"
            class="grid grid-cols-[96px_minmax(0,1fr)] items-baseline gap-2"
          >
            <dt class="truncate text-xs font-medium text-ink-gray-6">
              {{ fact.label }}
            </dt>
            <dd class="min-w-0 break-words text-xs text-ink-gray-8">
              {{ fact.value }}
            </dd>
          </div>
        </dl>
        <p
          v-if="doc.custom_triage_timestamp"
          class="mt-2 text-2xs text-ink-gray-5"
          :title="doc.custom_triage_timestamp"
        >
          {{ __("Triaged {0}", timeAgo(doc.custom_triage_timestamp)) }}
        </p>
      </template>
    </div>
  </PanelSection>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { TicketSymbol } from "@/types";
import { sanitizeRichText, timeAgo } from "@/utils";
import { computed, inject } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideLoaderCircle from "~icons/lucide/loader-circle";
import LucideScanSearch from "~icons/lucide/scan-search";
import PanelSection from "./PanelSection.vue";

// AI triage writes its result onto the ticket (custom_triage_* fields), so this
// reads the loaded document instead of calling the server
const ticket = inject(TicketSymbol)!;
const doc = computed(() => ticket.value.doc ?? {});
const status = computed<string>(() => doc.value.custom_triage_status || "");

const summary = computed(() =>
  sanitizeRichText(doc.value.custom_triage_summary)
);

const facts = computed(() =>
  [
    { label: __("Category"), value: doc.value.custom_triage_category },
    {
      label: __("Suggested priority"),
      value: doc.value.custom_triage_priority,
    },
    { label: __("Complexity"), value: doc.value.custom_triage_complexity },
    {
      label: __("Recommended track"),
      value: doc.value.custom_triage_recommended_track,
    },
  ].filter((fact) => fact.value)
);
</script>

<style scoped>
.triage-summary :deep(p + p) {
  @apply mt-2;
}
.triage-summary :deep(a) {
  @apply break-all text-ink-gray-9 underline underline-offset-2;
}
</style>

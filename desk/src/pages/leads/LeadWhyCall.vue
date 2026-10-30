<template>
  <section
    v-if="prospect && (prospect.why_call || chips.length)"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Why call')"
  >
    <h2
      class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
    >
      {{ __("Why call") }}
    </h2>
    <div class="flex flex-col gap-3 px-4 py-4">
      <p v-if="prospect.why_call" class="text-p-base text-ink-gray-8">
        {{ prospect.why_call }}
      </p>
      <ul v-if="chips.length" class="flex flex-wrap gap-1.5">
        <li
          v-for="chip in chips"
          :key="chip.key"
          class="inline-flex h-6 items-center gap-1 rounded-md px-2 text-xs"
          :class="
            chip.on
              ? 'bg-surface-gray-2 text-ink-gray-8'
              : 'border border-dashed border-outline-gray-3 text-ink-gray-6'
          "
        >
          <component :is="chip.icon" class="size-3.5" aria-hidden="true" />
          {{ chip.label }}
        </li>
      </ul>
      <p v-if="readOn" class="text-xs text-ink-gray-5">
        {{ __("Read from the website on {0}", readOn) }}
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { dayjs } from "frappe-ui";
import { computed } from "vue";
import { signalChips, type LeadProspect } from "./prospects";

const props = defineProps<{ prospect?: LeadProspect | null }>();

const chips = computed(() => signalChips(props.prospect));
const readOn = computed(() =>
  props.prospect?.read_on
    ? dayjs(props.prospect.read_on).format("D MMM YYYY")
    : ""
);
</script>

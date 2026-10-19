<template>
  <!-- a letter head's header or footer, as the client's page shows it -->
  <div class="px-6 py-3" :class="alignClass">
    <img
      v-if="part.image"
      :src="part.image"
      alt=""
      class="inline-block max-h-24 max-w-full"
    />
    <!-- sanitised on the ERP site and again by the hub (helpdesk.api.proposals) -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div
      v-else-if="part.html"
      class="text-p-sm text-ink-gray-8"
      v-html="part.html"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { LetterHeadPart } from "./proposals";

const props = defineProps<{ part: LetterHeadPart }>();

const alignClass = computed(
  () =>
    (({ center: "text-center", right: "text-right" } as Record<string, string>)[
      props.part.align || ""
    ] || "")
);
</script>

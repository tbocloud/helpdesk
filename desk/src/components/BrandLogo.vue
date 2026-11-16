<template>
  <img
    v-if="config.brandLogo && !failed"
    :src="config.brandLogo"
    :alt="config.brandName || ''"
    class="h-8 w-8 shrink-0 object-cover"
    @error="failed = true"
  />
  <span
    v-else
    class="grid size-8 shrink-0 place-items-center rounded-lg bg-brand text-sm font-semibold text-brand-on"
    aria-hidden="true"
  >
    {{ initials }}
  </span>
</template>

<script setup lang="ts">
import { useConfigStore } from "@/stores/config";
import { computed, ref, watch } from "vue";

const config = useConfigStore();
// a logo that doesn't load falls back to the initials tile, not broken-image alt text
const failed = ref(false);
watch(
  () => config.brandLogo,
  () => (failed.value = false)
);
const initials = computed(() =>
  (config.brandName || "").split(" ")[0].slice(0, 2).toUpperCase()
);
</script>

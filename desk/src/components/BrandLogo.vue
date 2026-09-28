<template>
  <img
    v-if="config.brandLogo"
    :src="config.brandLogo"
    alt="Brand Logo"
    class="h-8 w-8 shrink-0 object-cover"
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
import { computed } from "vue";

const config = useConfigStore();
const initials = computed(() =>
  (config.brandName || "").split(" ")[0].slice(0, 2).toUpperCase()
);
</script>

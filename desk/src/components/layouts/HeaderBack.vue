<template>
  <!-- back to the page they came from, as it was: its filters (in the URL) and how far
       down it was scrolled (router/scrollMemory.ts) -->
  <Button
    v-if="show"
    size="md"
    :tooltip="__('Back')"
    :aria-label="__('Back')"
    @click="router.back()"
  >
    <template #icon>
      <LucideArrowLeft class="size-4" aria-hidden="true" />
    </template>
  </Button>
</template>

<script setup lang="ts">
import { ownBackButtons } from "@/composables/goBack";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";

const route = useRoute();
const router = useRouter();

// history.state isn't reactive; vue-router writes it before it changes the route, so
// reading it when the route changes is current. No previous in-app page (opened
// directly, a new tab): nothing to go back to here.
const show = computed(() => {
  void route.fullPath;
  return Boolean(window.history.state?.back) && ownBackButtons.value === 0;
});
</script>

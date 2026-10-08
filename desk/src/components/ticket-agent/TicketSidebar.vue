<template>
  <!-- below lg the panel is a sheet over the conversation -->
  <div
    v-if="open"
    class="fixed inset-0 z-20 bg-black/30 lg:hidden"
    aria-hidden="true"
    @click="open = false"
  />
  <Resizer
    class="h-full flex-col border-l border-outline-gray-1 bg-surface-base max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-30 max-lg:!w-[min(24rem,100vw)] max-lg:shadow-xl"
    :class="open ? 'flex' : 'hidden lg:flex'"
    side="right"
  >
    <aside
      ref="panelRef"
      class="flex min-h-0 flex-1 flex-col focus:outline-none"
      :aria-label="__('Ticket details')"
      tabindex="-1"
      @keydown.esc="open = false"
    >
      <div
        class="flex h-12 shrink-0 items-center justify-between border-b border-outline-gray-1 px-5 lg:hidden"
      >
        <span class="text-base-medium text-ink-gray-9">
          {{ __("Details") }}
        </span>
        <Button
          variant="ghost"
          :aria-label="__('Close details')"
          @click="open = false"
        >
          <template #icon>
            <LucideX class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </div>
      <TicketDetailsTab />
    </aside>
  </Resizer>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { nextTick, ref, watch } from "vue";
import LucideX from "~icons/lucide/x";
import Resizer from "../Resizer.vue";
import TicketDetailsTab from "./TicketDetailsTab.vue";

/** The sheet is open; only matters below lg, where the panel isn't inline. */
const open = defineModel<boolean>("open", { default: false });

const panelRef = ref<HTMLElement | null>(null);
let returnFocusTo: HTMLElement | null = null;

watch(open, async (isOpen) => {
  if (isOpen) {
    returnFocusTo = document.activeElement as HTMLElement | null;
    await nextTick();
    panelRef.value?.focus();
  } else {
    returnFocusTo?.focus?.();
    returnFocusTo = null;
  }
});
</script>

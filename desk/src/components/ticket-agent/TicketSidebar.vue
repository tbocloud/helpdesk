<template>
  <!-- below lg the panel is a modal sheet over the conversation -->
  <div
    v-if="modal"
    class="fixed inset-0 z-20 bg-black/30"
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
      :role="modal ? 'dialog' : undefined"
      :aria-modal="modal ? 'true' : undefined"
      tabindex="-1"
      @keydown.tab="trapTab"
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
import { useEventListener } from "@vueuse/core";
import { computed, nextTick, ref, watch } from "vue";
import LucideX from "~icons/lucide/x";
import Resizer from "../Resizer.vue";
import TicketDetailsTab from "./TicketDetailsTab.vue";

const props = defineProps<{
  /** Below lg: the panel is a sheet rather than an inline column. */
  sheet: boolean;
}>();

const open = defineModel<boolean>("open", { default: false });
const modal = computed(() => props.sheet && open.value);

const panelRef = ref<HTMLElement | null>(null);
let opener: HTMLElement | null = null;

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]), [contenteditable="true"]';

// keep Tab inside the sheet while it is modal; popovers its fields open are
// teleported outside it and handle their own keys
function trapTab(e: KeyboardEvent) {
  if (!modal.value || !panelRef.value) return;
  const items = [
    ...panelRef.value.querySelectorAll<HTMLElement>(FOCUSABLE),
  ].filter((el) => el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  const active = document.activeElement;
  if (e.shiftKey && (active === first || active === panelRef.value)) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && active === last) {
    e.preventDefault();
    first.focus();
  }
}

// focus that leaves the sheet for the page behind it comes back; popovers and
// dialogs render outside #app (#popovers, #modals), so they keep theirs
useEventListener(document, "focusin", (e: FocusEvent) => {
  const target = e.target as HTMLElement | null;
  if (!modal.value || !panelRef.value || !target) return;
  if (panelRef.value.contains(target) || !target.closest("#app")) return;
  panelRef.value.focus();
});

// Esc anywhere closes the sheet, unless a dialog or menu on top of it takes it first
useEventListener(document, "keydown", (e: KeyboardEvent) => {
  if (e.key !== "Escape" || !modal.value || e.defaultPrevented) return;
  const layered = [
    ...document.querySelectorAll(
      '[role="dialog"], [role="menu"], [role="listbox"]'
    ),
  ].some((el) => el !== panelRef.value && !panelRef.value?.contains(el));
  if (layered) return;
  open.value = false;
});

watch(modal, async (isModal) => {
  if (isModal) {
    opener = document.activeElement as HTMLElement | null;
    await nextTick();
    panelRef.value?.focus();
  } else if (opener) {
    opener.focus?.();
    opener = null;
  }
});
</script>

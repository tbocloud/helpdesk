<template>
  <Dialog
    :open="current !== null"
    :title="current?.file_name || ''"
    size="4xl"
    @update:open="(v: boolean) => !v && close()"
  >
    <div v-if="current" class="flex flex-col gap-3">
      <div
        class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6"
      >
        <span v-if="items.length > 1" class="tabular-nums" aria-live="polite">
          {{ __("{0} of {1}", String(index + 1), String(items.length)) }}
        </span>
        <span v-if="current.uploaded_by_name">
          {{ __("Added by {0}", current.uploaded_by_name) }}
        </span>
        <span class="font-mono tabular-nums">{{
          formatBytes(current.file_size)
        }}</span>
      </div>

      <div
        class="relative flex min-h-[40vh] items-center justify-center overflow-hidden rounded-lg border border-outline-gray-2 bg-surface-gray-1"
      >
        <video
          v-if="current.kind === 'video'"
          :key="current.name"
          :src="current.file_url"
          :aria-label="current.file_name"
          controls
          playsinline
          preload="metadata"
          class="max-h-[68vh] w-full"
        />
        <img
          v-else
          :key="current.name"
          :src="current.file_url"
          :alt="current.file_name"
          class="max-h-[68vh] object-contain"
        />
        <template v-if="items.length > 1">
          <button
            type="button"
            class="absolute left-2 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-8 shadow-sm transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="__('Previous')"
            @click="step(-1)"
          >
            <LucideChevronLeft class="size-5" aria-hidden="true" />
          </button>
          <button
            type="button"
            class="absolute right-2 top-1/2 flex size-11 -translate-y-1/2 items-center justify-center rounded-full border border-outline-gray-2 bg-surface-base text-ink-gray-8 shadow-sm transition-colors hover:bg-surface-gray-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            :aria-label="__('Next')"
            @click="step(1)"
          >
            <LucideChevronRight class="size-5" aria-hidden="true" />
          </button>
        </template>
      </div>
    </div>

    <template #actions>
      <div
        v-if="current"
        class="flex flex-wrap items-center justify-between gap-2"
      >
        <!-- removing sits away from Download, and asks once before it goes -->
        <div class="flex flex-wrap items-center gap-2">
          <template v-if="current.can_delete">
            <template v-if="confirming">
              <span class="text-p-sm text-ink-gray-7" role="alert">
                {{ __("Remove it for everyone?") }}
              </span>
              <Button :label="__('Keep')" @click="confirming = false" />
              <Button
                theme="red"
                variant="solid"
                :label="__('Remove file')"
                :loading="removing"
                @click="emit('remove', current)"
              />
            </template>
            <Button v-else :label="__('Remove')" @click="confirming = true">
              <template #prefix>
                <LucideTrash2 class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </template>
        </div>
        <a
          :href="downloadHref(current.file_url)"
          :download="current.file_name"
          class="inline-flex h-7 items-center gap-1.5 rounded bg-surface-gray-2 px-2 text-base text-ink-gray-8 transition-colors hover:bg-surface-gray-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          <LucideDownload class="size-4" aria-hidden="true" />
          {{ __("Download") }}
        </a>
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import { downloadHref, formatBytes } from "@/pages/tasky/projectFiles";
import { __ } from "@/translation";
import { Button, Dialog } from "frappe-ui";
import { useEventListener } from "@vueuse/core";
import { computed, ref, watch } from "vue";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideDownload from "~icons/lucide/download";
import LucideTrash2 from "~icons/lucide/trash-2";

/** An image or video the lightbox can show. */
export interface MediaItem {
  name: string;
  file_name: string;
  file_url: string;
  file_size?: number;
  kind: "image" | "video";
  uploaded_by_name?: string;
  /** Offers Remove, which emits `remove`; the opener deletes it. */
  can_delete?: boolean;
}

const props = defineProps<{
  items: MediaItem[];
  /** The item shown; the lightbox is open while this is a number. */
  index: number | null;
  /** The opener is deleting the item. */
  removing?: boolean;
}>();

const emit = defineEmits<{
  "update:index": [value: number | null];
  remove: [item: MediaItem];
}>();

const confirming = ref(false);
const current = computed(() =>
  props.index === null ? null : props.items[props.index] ?? null
);

watch(
  () => current.value?.name,
  () => (confirming.value = false)
);

function close() {
  emit("update:index", null);
}

function step(by: number) {
  const count = props.items.length;
  if (props.index === null || count < 2) return;
  emit("update:index", (props.index + by + count) % count);
}

// arrow keys belong to a focused video (seeking) and to text fields
useEventListener(document, "keydown", (event: KeyboardEvent) => {
  if (current.value === null || event.defaultPrevented) return;
  if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
  const target = event.target as HTMLElement | null;
  if (target?.closest("video, input, textarea, [contenteditable]")) return;
  event.preventDefault();
  step(event.key === "ArrowLeft" ? -1 : 1);
});
</script>

<template>
  <Teleport to="#app-header" v-if="showHeader">
    <slot>
      <!-- the page's title and its actions, sitting on the canvas above the page's cards -->
      <header
        class="mx-4 flex min-h-12 flex-wrap items-center justify-between gap-x-4 gap-y-2 md:mx-0 md:min-h-9 md:items-end"
      >
        <div class="flex min-w-0 flex-1 items-center gap-2">
          <div v-if="title" class="flex min-w-0 flex-col gap-1">
            <h1
              class="truncate text-lg font-bold text-ink-gray-9 md:text-[22px] md:leading-[1.25] md:tracking-[-0.01em]"
            >
              {{ title }}
            </h1>
            <p v-if="subtitle" class="hidden text-sm text-ink-gray-6 md:block">
              {{ subtitle }}
            </p>
          </div>
          <slot name="left-header" />
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-2.5">
          <slot name="right-header" />
        </div>
      </header>
    </slot>
  </Teleport>
</template>
<script setup lang="ts">
import { nextTick, ref } from "vue";

defineProps<{
  /** the page's name, as the page's one h1 */
  title?: string;
  /** one sentence under the title on wider screens: what the page is for */
  subtitle?: string;
}>();

const showHeader = ref(false);

nextTick(() => {
  showHeader.value = true;
});
</script>

<template>
  <section
    :class="flush && showBody ? 'pt-4' : 'py-4'"
    :aria-labelledby="headingId"
  >
    <div
      class="flex min-h-6 items-center justify-between gap-2 px-5"
      :class="{ 'mb-2.5': showBody && !flush }"
    >
      <component
        :is="`h${level}`"
        :id="headingId"
        class="min-w-0 flex-1 text-2xs font-semibold uppercase tracking-[0.06em] text-ink-gray-5"
      >
        <button
          v-if="collapsible"
          type="button"
          class="-mx-1 flex w-[calc(100%+0.5rem)] items-center gap-1.5 rounded px-1 text-start uppercase hover:text-ink-gray-8"
          :aria-expanded="opened"
          :aria-controls="bodyId"
          @click="opened = !opened"
        >
          <component
            :is="icon"
            v-if="icon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          />
          <span class="truncate">{{ title }}</span>
          <span
            v-if="count"
            class="font-mono font-normal tabular-nums text-ink-gray-5"
          >
            {{ count }}
          </span>
          <LucideChevronRight
            class="ms-auto size-4 shrink-0 transition-transform"
            :class="{ 'rotate-90': opened }"
            aria-hidden="true"
          />
        </button>
        <span v-else class="flex min-w-0 items-center gap-1.5">
          <component
            :is="icon"
            v-if="icon"
            class="size-3.5 shrink-0"
            aria-hidden="true"
          />
          <span class="truncate">{{ title }}</span>
          <span
            v-if="count"
            class="font-mono font-normal tabular-nums text-ink-gray-5"
          >
            {{ count }}
          </span>
        </span>
      </component>
      <div
        v-if="$slots.actions"
        class="flex shrink-0 items-center gap-1 normal-case"
      >
        <slot name="actions" />
      </div>
    </div>
    <div v-show="showBody" :id="bodyId" :class="{ 'px-5': !flush }">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, useId, type Component } from "vue";
import LucideChevronRight from "~icons/lucide/chevron-right";

/**
 * One titled block of the ticket side panel: the eyebrow heading every panel
 * section shares, optionally collapsible (v-model:opened).
 */
const props = withDefaults(
  defineProps<{
    title: string;
    icon?: Component;
    count?: number;
    collapsible?: boolean;
    /** Sections inside a group (the AI group's cards) are level 3. */
    level?: 2 | 3;
    /** The body runs edge to edge, for nested sections that pad themselves. */
    flush?: boolean;
  }>(),
  { level: 2 }
);

const opened = defineModel<boolean>("opened", { default: true });

const headingId = `panel-section-${useId()}`;
const bodyId = `${headingId}-body`;
const showBody = computed(() => !props.collapsible || opened.value);
</script>

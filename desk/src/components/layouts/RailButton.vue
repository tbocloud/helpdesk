<template>
  <!-- no delay: the icons carry no words, so the name shows the moment a pointer or the keyboard lands -->
  <Tooltip :text="label" placement="right" :hover-delay="0" :disabled="mobile">
    <button
      type="button"
      class="relative grid shrink-0 place-items-center rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      :class="[
        mobile ? 'size-11' : 'size-10',
        active
          ? 'bg-brand text-brand-on'
          : 'text-[color:var(--ink-rail)] hover:bg-[color:var(--rail-hover)] hover:text-[color:var(--ink-rail-hover)]',
        // a marker on the rail's edge: the area being viewed, or the one holding the open page
        (active || current) &&
          'before:absolute before:inset-y-2 before:-start-2 before:w-[3px] before:rounded-e-full before:bg-[color:var(--ink-rail-hover)]',
      ]"
      :aria-label="label"
      v-bind="$attrs"
    >
      <slot />
      <span
        v-if="dot"
        class="absolute end-1.5 top-1.5 size-2 rounded-full bg-brand ring-2 ring-[color:var(--surface-rail)]"
        aria-hidden="true"
      />
    </button>
  </Tooltip>
</template>

<script setup lang="ts">
import { Tooltip } from "frappe-ui";

defineOptions({ inheritAttrs: false });

defineProps<{
  label: string;
  active?: boolean;
  /** holds the page being viewed while another area is selected */
  current?: boolean;
  /** an unread marker; the count itself lives in the label */
  dot?: boolean;
  mobile?: boolean;
}>();
</script>

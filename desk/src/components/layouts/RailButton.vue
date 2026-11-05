<template>
  <Tooltip :text="label" placement="right" :disabled="mobile">
    <button
      type="button"
      class="relative grid shrink-0 place-items-center rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
      :class="[
        mobile ? 'size-11' : 'size-10',
        active
          ? 'bg-brand text-brand-on'
          : 'text-[color:var(--ink-rail)] hover:bg-[color:var(--rail-hover)]',
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
  /** an unread marker; the count itself lives in the label */
  dot?: boolean;
  mobile?: boolean;
}>();
</script>

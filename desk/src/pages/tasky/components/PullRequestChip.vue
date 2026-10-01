<template>
  <!-- inside a row that is itself a link, render as plain text: links can't nest -->
  <component
    :is="plain ? 'span' : 'a'"
    v-bind="
      plain
        ? {}
        : { href: pr.url, target: '_blank', rel: 'noopener noreferrer' }
    "
    class="inline-flex h-5 shrink-0 items-center gap-1 whitespace-nowrap rounded-md px-1.5 font-mono text-xs font-medium tabular-nums focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :class="TONE_CLASSES[signal.tone]"
    :title="description"
    :aria-label="description"
    draggable="false"
    @click="!plain && $event.stopPropagation()"
  >
    <component :is="signal.icon" class="size-3.5" aria-hidden="true" />
    <span aria-hidden="true">#{{ pr.number }}</span>
  </component>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  prDescription,
  prSignal,
  type TaskPullRequest,
} from "../pullRequestMeta";
import { TONE_CLASSES } from "../taskMeta";

const props = defineProps<{
  /** The task's most recently active open PR. */
  pr: TaskPullRequest;
  /** Text instead of a link, for use inside a row that is a link. */
  plain?: boolean;
}>();

const signal = computed(() => prSignal(props.pr));
const description = computed(() => prDescription(props.pr));
</script>

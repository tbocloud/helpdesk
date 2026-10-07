<template>
  <!-- the header of a customer or contact page: who it is, the key facts, the actions -->
  <div
    class="flex flex-col gap-4 px-5 pt-5 sm:flex-row sm:items-start sm:justify-between"
  >
    <div class="flex min-w-0 items-start gap-3">
      <Avatar
        :size="avatar.size ?? '3xl'"
        :shape="avatar.shape ?? 'square'"
        :label="avatar.label"
        :image="avatar.image"
        class="shrink-0"
      />
      <div class="flex min-w-0 flex-col gap-1.5">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <h1 class="min-w-0 break-words text-xl-semibold text-ink-gray-9">
            {{ avatar.label }}
          </h1>
          <TaskyBadge
            v-if="badge"
            :label="badge.label"
            :tone="badge.tone"
            :icon="badge.icon"
            :title="badge.tooltip"
          />
        </div>
        <ul
          v-if="shownInfo.length"
          role="list"
          class="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1"
        >
          <li
            v-for="(item, index) in shownInfo"
            :key="index"
            class="flex min-w-0 items-center gap-1.5 text-sm text-ink-gray-7"
          >
            <component
              :is="item.icon"
              v-if="item.icon"
              class="size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <span v-if="item.value" class="truncate" :title="item.value">
              {{ item.value }}
            </span>
            <component :is="item.component" v-else-if="item.component" />
          </li>
        </ul>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-2">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { Avatar, type AvatarProps } from "frappe-ui";
import { computed, type Component } from "vue";

interface DocInfoItem {
  icon?: Component;
  value?: string;
  component?: Component;
  condition?: boolean;
}

interface BadgeInfo {
  label: string;
  tone?: Tone;
  icon?: Component;
  tooltip?: string;
}

const props = withDefaults(
  defineProps<{
    avatar: AvatarProps;
    docInfo?: DocInfoItem[];
    badge?: BadgeInfo | null;
  }>(),
  {
    docInfo: () => [],
    badge: null,
  }
);

const shownInfo = computed(() =>
  props.docInfo.filter((item) => item.condition !== false)
);
</script>

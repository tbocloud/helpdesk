<template>
  <TaskyState
    v-if="error"
    error
    :icon="LucideCircleAlert"
    :title="__('Couldn\'t load this list')"
    :message="errorText(error, __('Check your connection, then try again.'))"
  >
    <template v-if="onRetry" #default>
      <Button :label="__('Try again')" @click="onRetry()" />
    </template>
  </TaskyState>
  <div
    v-else-if="loading && !items?.length"
    class="overflow-hidden rounded-lg border border-outline-gray-2"
    aria-busy="true"
    :aria-label="__('Loading')"
  >
    <div
      v-for="i in 4"
      :key="i"
      class="flex h-14 items-center gap-3 border-t border-outline-gray-1 px-3 first:border-t-0"
    >
      <div class="h-4 w-1/3 animate-pulse rounded bg-surface-gray-2" />
      <div class="ms-auto h-4 w-16 animate-pulse rounded bg-surface-gray-2" />
    </div>
  </div>
  <TaskyState
    v-else-if="!items?.length && filtered"
    :icon="LucideSearchX"
    :title="__('Nothing matches')"
    :message="__('Try another search or filter.')"
  >
    <template v-if="onClearFilters" #default>
      <Button :label="__('Clear search')" @click="onClearFilters()" />
    </template>
  </TaskyState>
  <TaskyState
    v-else-if="!items?.length"
    :icon="emptyIcon"
    :title="emptyTitle"
    :message="emptyMessage"
  />
  <div v-else class="flex flex-col gap-3">
    <div class="overflow-hidden rounded-lg border border-outline-gray-2">
      <div
        v-if="$slots.header"
        class="hidden items-center gap-3 border-b border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-sm text-ink-gray-6 sm:flex"
        aria-hidden="true"
      >
        <slot name="header" />
      </div>
      <ul class="divide-y divide-outline-gray-1" :aria-label="label">
        <li v-for="(item, index) in items" :key="itemKey(item, index)">
          <slot :item="item" :index="index" />
        </li>
      </ul>
    </div>
    <div v-if="hasMore && onMore" class="flex justify-center">
      <Button :label="__('Show more')" :loading="loading" @click="onMore()" />
    </div>
  </div>
</template>

<script setup lang="ts" generic="T">
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import type { Component } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideSearchX from "~icons/lucide/search-x";

const props = defineProps<{
  items?: T[] | null;
  /** Accessible name of the list, e.g. "SLA policies". */
  label: string;
  loading?: boolean;
  error?: unknown;
  emptyIcon: Component;
  emptyTitle: string;
  /** Says what the list is for and points at the page's primary action. */
  emptyMessage?: string;
  /** A search or filter is on: an empty result says "Nothing matches". */
  filtered?: boolean;
  hasMore?: boolean;
  /** Key of each row; defaults to `item.name`. */
  rowKey?: string;
  onRetry?: () => void;
  onMore?: () => void;
  onClearFilters?: () => void;
}>();

defineSlots<{
  default(props: { item: T; index: number }): unknown;
  header?(): unknown;
}>();

function itemKey(item: T, index: number) {
  const key = (item as Record<string, unknown>)?.[props.rowKey || "name"];
  return (key as string) ?? index;
}
</script>

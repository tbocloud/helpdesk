<template>
  <!-- a list of article rows with its loading, error and empty states -->
  <ul
    v-if="loading && !articles?.length"
    class="flex flex-col"
    aria-busy="true"
    :aria-label="__('Loading articles')"
  >
    <li
      v-for="i in skeletonRows"
      :key="i"
      class="flex flex-col gap-2 px-4 py-3"
    >
      <span class="h-4 w-2/3 animate-pulse rounded bg-surface-gray-2" />
      <span class="h-3 w-1/3 animate-pulse rounded bg-surface-gray-2" />
    </li>
  </ul>
  <div
    v-else-if="error"
    class="flex flex-wrap items-center gap-3 px-4 py-4 text-p-sm text-ink-gray-6"
    role="alert"
  >
    <LucideCircleAlert class="size-4 shrink-0 text-danger" aria-hidden="true" />
    <span class="min-w-0 flex-1">
      {{ errorText(error, __("These articles didn't load.")) }}
    </span>
    <Button :label="__('Retry')" @click="emit('retry')" />
  </div>
  <p v-else-if="!articles?.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
    {{ emptyText }}
  </p>
  <ul v-else class="flex flex-col divide-y divide-outline-gray-1">
    <li v-for="article in articles" :key="article.name">
      <ArticleCard :article="article" />
    </li>
  </ul>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import ArticleCard, { type ArticleSummary } from "./ArticleCard.vue";

withDefaults(
  defineProps<{
    articles?: ArticleSummary[] | null;
    loading?: boolean;
    error?: unknown;
    emptyText: string;
    skeletonRows?: number;
  }>(),
  { articles: () => [], loading: false, error: null, skeletonRows: 3 }
);

const emit = defineEmits<{ retry: [] }>();
</script>

<template>
  <RouterLink
    class="flex h-full min-w-0 items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-base px-4 py-3 transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :to="{ name: 'Articles', params: { categoryId: category.name } }"
  >
    <LucideFolder class="size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
    <span class="flex min-w-0 flex-1 flex-col">
      <span class="truncate text-base font-medium text-ink-gray-9">
        {{ category.category_name }}
      </span>
      <span class="text-sm tabular-nums text-ink-gray-6">
        {{
          category.article_count === 1
            ? __("1 article")
            : __("{0} articles", [category.article_count])
        }}
      </span>
    </span>
    <LucideChevronRight
      class="size-4 shrink-0 text-ink-gray-4"
      aria-hidden="true"
    />
  </RouterLink>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideFolder from "~icons/lucide/folder";

defineProps<{
  category: { name: string; category_name: string; article_count: number };
}>();
</script>

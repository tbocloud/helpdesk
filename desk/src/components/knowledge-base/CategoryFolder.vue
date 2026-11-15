<template>
  <RouterLink
    class="flex h-full min-w-0 items-center gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4 transition-colors hover:border-outline-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
    :to="{ name: 'Articles', params: { categoryId: category.name } }"
  >
    <span
      class="grid size-9 shrink-0 place-items-center rounded-[10px] bg-brand-soft text-brand-ink"
    >
      <LucideFolder class="size-[18px]" aria-hidden="true" />
    </span>
    <span class="flex min-w-0 flex-1 flex-col">
      <span class="truncate text-[14px] font-semibold text-ink-gray-9">
        {{ category.category_name }}
      </span>
      <span class="text-[12px] tabular-nums text-ink-gray-6">
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

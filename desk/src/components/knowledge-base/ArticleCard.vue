<template>
  <!-- one article as a row: title, an optional excerpt, and where/when it's from -->
  <RouterLink
    class="flex min-w-0 items-start gap-3 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
    :to="{ name: 'ArticlePublic', params: { articleId: article.name } }"
  >
    <LucideFileText
      class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
      aria-hidden="true"
    />
    <span class="flex min-w-0 flex-1 flex-col gap-1">
      <span class="text-base font-medium text-ink-gray-9">
        {{ article.title }}
      </span>
      <span
        v-if="article.content"
        class="line-clamp-2 text-p-sm text-ink-gray-6"
      >
        {{ article.content }}
      </span>
      <span
        v-if="meta.length"
        class="flex flex-wrap items-center gap-x-1.5 text-sm text-ink-gray-5"
      >
        <template v-for="(part, i) in meta" :key="part">
          <span v-if="i" aria-hidden="true">·</span>
          <span>{{ part }}</span>
        </template>
      </span>
    </span>
  </RouterLink>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { timeAgo } from "@/utils";
import { computed } from "vue";
import LucideFileText from "~icons/lucide/file-text";

export interface ArticleSummary {
  name: string;
  title: string;
  /** plain-text excerpt */
  content?: string;
  category_name?: string | null;
  author?: { name: string } | null;
  modified?: string;
}

const props = defineProps<{ article: ArticleSummary }>();

const meta = computed(() =>
  [
    props.article.category_name,
    props.article.author?.name && __("By {0}", [props.article.author.name]),
    props.article.modified &&
      __("Updated {0}", [timeAgo(props.article.modified)]),
  ].filter(Boolean)
);
</script>

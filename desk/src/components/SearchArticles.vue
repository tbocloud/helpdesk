<template>
  <!-- knowledge-base answers for what the customer is typing (ticket deflection) -->
  <section
    v-if="query.length > 2 && articles.data?.length"
    class="rounded-lg border border-outline-gray-2 bg-surface-base"
    aria-live="polite"
    :aria-label="__('Suggested articles')"
  >
    <div
      v-if="!hideViewAll"
      class="flex items-center justify-between gap-3 px-4 pb-1 pt-3"
    >
      <h2 class="text-sm font-medium text-ink-gray-8">
        {{ __("These articles may already answer it") }}
      </h2>
      <RouterLink
        :to="{ name: 'CustomerKnowledgeBase' }"
        target="_blank"
        class="shrink-0 rounded text-sm text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
      >
        {{ __("Browse all") }}
        <span class="sr-only">{{ __("(opens in a new tab)") }}</span>
      </RouterLink>
    </div>
    <ul class="flex flex-col py-1.5">
      <li v-for="a in articles.data" :key="a.id">
        <RouterLink
          class="flex flex-col gap-0.5 px-4 py-2 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-outline-gray-4"
          :to="{
            name: 'ArticlePublic',
            params: { articleId: a.name.split('#')[0] },
            hash: a.name.includes('#') ? `#${a.name.split('#')[1]}` : '',
          }"
          target="_blank"
          @click="handleSearchArticleClick(a)"
        >
          <span class="text-base font-medium text-ink-gray-9">
            {{ a.subject }}
            <span v-if="a.headings" class="font-normal text-ink-gray-6">
              · {{ a.headings }}
            </span>
            <span class="sr-only">{{ __("(opens in a new tab)") }}</span>
          </span>
          <!-- eslint-disable-next-line vue/no-v-html -->
          <span
            class="line-clamp-2 text-p-sm text-ink-gray-6"
            v-html="sanitizeRichText(a.description)"
          />
        </RouterLink>
      </li>
    </ul>
  </section>
  <p
    v-else-if="query.length > 2 && articles.loading"
    class="flex items-center gap-2 px-1 text-p-sm text-ink-gray-6"
    aria-live="polite"
  >
    <LoadingIndicator class="size-4" />
    {{ __("Looking for articles that may help…") }}
  </p>
  <p
    v-else-if="query.length > 2 && articles.error"
    class="px-1 text-p-sm text-ink-gray-6"
    role="status"
  >
    {{ __("Article suggestions aren't available right now.") }}
  </p>
  <p
    v-else-if="query.length > 2 && articles.data?.length === 0"
    class="flex items-center gap-2 px-1 text-p-sm text-ink-gray-6"
    aria-live="polite"
  >
    <LucideSearch class="size-4 shrink-0 text-ink-gray-5" aria-hidden="true" />
    {{
      hideViewAll
        ? __("No articles match that. Try other words.")
        : __("No articles match yet. Describe the problem and we'll help.")
    }}
  </p>
</template>

<script setup lang="ts">
import { capture } from "@/telemetry";
import { __ } from "@/translation";
import { sanitizeRichText } from "@/utils";
import { createResource, LoadingIndicator } from "frappe-ui";
import { watch } from "vue";
import LucideSearch from "~icons/lucide/search";

interface P {
  query: string;
  hideViewAll?: boolean;
}

const { query = "", hideViewAll = false } = defineProps<P>();
const articles = createResource({
  url: "helpdesk.api.article.search",
  debounce: 500,
  auto: false,
});
watch(
  () => query,
  (query) => {
    if (query.length < 3) return;
    articles.update({
      params: {
        query: query,
      },
    });
    articles.reload();
  }
);

function handleSearchArticleClick(article) {
  capture("kb_customer_search_article_clicked", {
    data: {
      article: article.subject,
    },
  });
}
</script>

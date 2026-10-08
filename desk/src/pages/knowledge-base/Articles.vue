<template>
  <div class="flex flex-col overflow-y-auto">
    <LayoutHeader>
      <template #left-header>
        <Breadcrumbs :items="breadcrumbs" class="-ml-0.5" />
      </template>
    </LayoutHeader>
    <div class="mx-auto flex w-full max-w-3xl flex-col gap-4 px-4 py-6 md:px-6">
      <div class="flex flex-col gap-1">
        <h1 class="text-2xl font-semibold text-ink-gray-9">
          <span
            v-if="categoryName.loading"
            class="inline-block h-7 w-48 animate-pulse rounded bg-surface-gray-2 align-middle"
          />
          <template v-else>{{ categoryTitle }}</template>
        </h1>
        <p
          v-if="articles.data?.length"
          class="text-sm tabular-nums text-ink-gray-6"
        >
          {{
            articles.data.length === 1
              ? __("1 article")
              : __("{0} articles", [articles.data.length])
          }}
        </p>
      </div>
      <div class="rounded-lg border border-outline-gray-2 bg-surface-base">
        <ArticleList
          :articles="articles.data"
          :loading="articles.loading"
          :error="articles.error"
          :empty-text="__('There are no published articles in this topic yet.')"
          :skeleton-rows="5"
          @retry="articles.reload()"
        />
      </div>
      <p class="text-p-sm text-ink-gray-6">
        <RouterLink
          :to="{ name: 'CustomerKnowledgeBase' }"
          class="rounded font-medium text-ink-gray-8 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ __("All topics") }}
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import ArticleList from "@/components/knowledge-base/ArticleList.vue";
import LayoutHeader from "@/components/LayoutHeader.vue";
import { categoryName } from "@/stores/knowledgeBase";
import { capture } from "@/telemetry";
import { __ } from "@/translation";
import { Breadcrumbs, createResource, usePageMeta } from "frappe-ui";
import { computed, onMounted } from "vue";

const props = defineProps({
  categoryId: {
    required: true,
    type: String,
  },
});

const articles = createResource({
  url: "helpdesk.api.knowledge_base.get_category_articles",
  cache: ["articles", props.categoryId],
  params: {
    category: props.categoryId,
  },
  auto: true,
});

onMounted(() => {
  categoryName.fetch({
    category: props.categoryId,
  });
  capture("kb_customer_page_articles", {
    data: {
      category: props.categoryId,
    },
  });
});

// a failed or empty lookup still names the page
const categoryTitle = computed(() =>
  categoryName.loading ? "" : categoryName.data || __("Topic")
);

const breadcrumbs = computed(() => [
  {
    label: __("Knowledge base"),
    route: { name: "CustomerKnowledgeBase" },
  },
  { label: categoryTitle.value },
]);

usePageMeta(() => {
  return {
    title: categoryTitle.value
      ? `${categoryTitle.value} - ${__("Knowledge base")}`
      : __("Knowledge base"),
  };
});
</script>

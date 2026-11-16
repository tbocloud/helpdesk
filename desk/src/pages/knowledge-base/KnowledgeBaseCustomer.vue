<template>
  <div class="flex flex-col overflow-y-auto">
    <LayoutHeader
      :title="__('Knowledge base')"
      :subtitle="
        __('Guides from our team, to sort things out without waiting.')
      "
    >
      <template #right-header>
        <RouterLink class="inline-flex" :to="{ name: 'TicketNew' }">
          <Button size="md" :label="__('New ticket')">
            <template #prefix>
              <LucidePlus class="size-[18px]" aria-hidden="true" />
            </template>
          </Button>
        </RouterLink>
      </template>
    </LayoutHeader>

    <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
      <!-- search is the page's one job -->
      <section
        class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
        aria-labelledby="kb-search-heading"
      >
        <div class="flex flex-col gap-1">
          <h2
            id="kb-search-heading"
            class="text-xl font-semibold text-ink-gray-9"
          >
            {{ __("How can we help?") }}
          </h2>
          <p class="text-[14px] text-ink-gray-6">
            {{ __("Search our guides, or browse them by topic.") }}
          </p>
        </div>
        <label for="kb-search" class="sr-only">
          {{ __("Search articles") }}
        </label>
        <FormControl
          id="kb-search"
          v-model="query"
          type="search"
          size="md"
          autofocus
          :placeholder="__('Search, e.g. reset password')"
        >
          <template #prefix>
            <LucideSearch
              class="size-[18px] text-ink-gray-6"
              aria-hidden="true"
            />
          </template>
        </FormControl>
        <SearchArticles :query="query" hide-view-all />
      </section>

      <section class="flex flex-col gap-3" aria-labelledby="kb-topics-heading">
        <h2
          id="kb-topics-heading"
          class="text-base font-semibold text-ink-gray-9"
        >
          {{ __("Browse by topic") }}
        </h2>
        <CategoryFolderContainer />
      </section>

      <div class="grid grid-cols-1 gap-5 md:grid-cols-2">
        <SectionCard :title="__('Most read')">
          <ArticleList
            :articles="featured.data?.popular"
            :loading="featured.loading"
            :error="featured.error"
            :empty-text="
              __(
                'Once people start reading, the most useful guides show up here.'
              )
            "
            @retry="featured.reload()"
          />
        </SectionCard>
        <SectionCard :title="__('Recently updated')">
          <ArticleList
            :articles="featured.data?.recent"
            :loading="featured.loading"
            :error="featured.error"
            :empty-text="__('No articles published yet.')"
            @retry="featured.reload()"
          />
        </SectionCard>
      </div>

      <p class="text-p-sm text-ink-gray-6">
        {{ __("Can't find what you need?") }}
        <RouterLink
          :to="{ name: 'TicketNew' }"
          class="rounded font-medium text-ink-gray-8 underline underline-offset-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ __("Raise a ticket") }}
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { LayoutHeader } from "@/components";
import ArticleList from "@/components/knowledge-base/ArticleList.vue";
import CategoryFolderContainer from "@/components/knowledge-base/CategoryFolderContainer.vue";
import SearchArticles from "@/components/SearchArticles.vue";
import SectionCard from "@/components/SectionCard.vue";
import { capture } from "@/telemetry";
import { __ } from "@/translation";
import { Button, createResource, FormControl, usePageMeta } from "frappe-ui";
import { onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucidePlus from "~icons/lucide/plus";
import LucideSearch from "~icons/lucide/search";

const route = useRoute();
const router = useRouter();

// the search lives in the URL, so a result can be shared or come back to
const query = ref((route.query.q as string) || "");
watch(query, (q) => {
  if (q === ((route.query.q as string) || "")) return;
  router.replace({ query: { ...route.query, q: q || undefined } });
});
// back/forward or a link that changes ?q= while the page stays open
watch(
  () => route.query.q,
  (q) => {
    query.value = (q as string) || "";
  }
);

const featured = createResource({
  url: "helpdesk.api.knowledge_base.get_featured_articles",
  cache: ["kbFeaturedArticles"],
  auto: true,
});

onMounted(() => {
  capture("kb_customer_page_viewed");
});
usePageMeta(() => {
  return {
    title: __("Knowledge base"),
  };
});
</script>

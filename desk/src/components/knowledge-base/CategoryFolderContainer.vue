<template>
  <ul
    v-if="categories.loading && !categories.data"
    class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
    aria-busy="true"
    :aria-label="__('Loading topics')"
  >
    <li
      v-for="i in 6"
      :key="i"
      class="h-[62px] animate-pulse rounded-lg bg-surface-gray-2"
    />
  </ul>
  <TaskyState
    v-else-if="categories.error"
    :icon="LucideCircleAlert"
    :title="__('Topics didn\'t load')"
    :message="
      errorText(categories.error, __('Check your connection and try again.'))
    "
    error
  >
    <Button :label="__('Retry')" @click="categories.reload()" />
  </TaskyState>
  <TaskyState
    v-else-if="!categories.data?.length"
    :icon="LucideBookOpen"
    :title="__('No articles published yet')"
    :message="
      __('When our team publishes guides, you\'ll find them here by topic.')
    "
  />
  <ul v-else class="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
    <li v-for="category in categories.data" :key="category.name">
      <CategoryFolder :category="category" />
    </li>
  </ul>
</template>

<script setup lang="ts">
import TaskyState from "@/components/TaskyState.vue";
import { categories } from "@/stores/knowledgeBase";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button } from "frappe-ui";
import { onMounted } from "vue";
import LucideBookOpen from "~icons/lucide/book-open";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import CategoryFolder from "./CategoryFolder.vue";

onMounted(() => {
  categories.fetch();
});
</script>

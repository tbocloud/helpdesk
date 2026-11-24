<template>
  <div v-if="scope || checks?.length" class="flex flex-col gap-2 text-p-sm">
    <div v-if="scope">
      <h4 class="text-xs text-ink-gray-5">{{ __("What we will build") }}</h4>
      <p class="whitespace-pre-line text-ink-gray-8">{{ scope }}</p>
    </div>
    <div v-if="checks?.length">
      <h4 class="text-xs text-ink-gray-5">{{ __("Done when") }}</h4>
      <ul class="ml-4 list-disc text-ink-gray-8">
        <li v-for="check in checks" :key="check">{{ check }}</li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { __ } from "@/translation";

defineProps<{ scope?: string; checks?: string[] }>();
</script>

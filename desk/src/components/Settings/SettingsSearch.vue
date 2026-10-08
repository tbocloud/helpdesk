<template>
  <TextInput
    v-model="query"
    type="text"
    class="min-w-0 flex-1"
    :placeholder="placeholder"
    :aria-label="placeholder"
    :debounce="300"
  >
    <template #prefix>
      <LucideSearch class="size-4 text-ink-gray-5" aria-hidden="true" />
    </template>
    <template v-if="query" #suffix>
      <Button
        variant="ghost"
        size="sm"
        :label="__('Clear search')"
        @click="query = ''"
      >
        <template #icon>
          <LucideX class="size-3.5" aria-hidden="true" />
        </template>
      </Button>
    </template>
  </TextInput>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { Button, TextInput } from "frappe-ui";
import LucideSearch from "~icons/lucide/search";
import LucideX from "~icons/lucide/x";

defineProps<{ placeholder: string }>();

const query = defineModel<string>({ default: "" });
</script>

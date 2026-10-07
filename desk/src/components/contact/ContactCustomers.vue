<template>
  <!-- the customers a contact belongs to, each a link to its page -->
  <span v-if="customers.length" class="flex min-w-0 items-center gap-1.5">
    <LucideBuilding2
      class="size-4 shrink-0 text-ink-gray-5"
      aria-hidden="true"
    />
    <span class="sr-only">{{ __("Customers:") }}</span>
    <span class="flex min-w-0 flex-wrap items-center gap-x-1">
      <template v-for="(customer, index) in customers" :key="customer.name">
        <RouterLink
          :to="{ name: 'Customer', params: { id: customer.name } }"
          class="rounded text-ink-gray-8 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ customer.name }}</RouterLink
        ><span v-if="index < customers.length - 1" aria-hidden="true">,</span>
      </template>
    </span>
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import { RouterLink } from "vue-router";
import LucideBuilding2 from "~icons/lucide/building-2";

interface Customer {
  name: string;
}

defineProps<{
  customers: Customer[];
}>();
</script>

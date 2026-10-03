<template>
  <span class="inline-flex shrink-0 items-center" :title="__('Milestone')">
    <LucideFlag class="size-3.5 fill-current text-info" aria-hidden="true" />
    <span class="sr-only">{{ __("Milestone") }}</span>
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import LucideFlag from "~icons/lucide/flag";
</script>

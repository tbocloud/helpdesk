<template>
  <span
    class="inline-flex h-5 items-center gap-1 rounded-full bg-surface-gray-2 px-2 text-xs text-ink-gray-6"
    :title="__('Written by the AI; nobody has edited it yet.')"
  >
    <LucideSparkles class="size-3" aria-hidden="true" />
    {{ __("AI drafted") }}
  </span>
</template>

<script setup lang="ts">
import { __ } from "@/translation";
import LucideSparkles from "~icons/lucide/sparkles";
</script>

<template>
  <div class="flex flex-col gap-1.5">
    <h4 class="text-base-medium text-ink-gray-9">{{ title }}</h4>
    <ul class="flex flex-wrap gap-1" role="list">
      <li
        v-for="(c, i) in cases"
        :key="i"
        class="inline-flex h-7 min-w-[2.75rem] items-center justify-center gap-1 rounded px-1.5 text-xs font-medium"
        :class="
          c.right
            ? 'bg-success-soft text-success'
            : 'bg-danger-soft text-danger'
        "
        :title="c.right ? __('{0}: right', c.case) : __('{0}: wrong', c.case)"
      >
        <component
          :is="c.right ? LucideCheck : LucideX"
          class="size-3"
          aria-hidden="true"
        />
        {{ c.case }}
        <span class="sr-only">{{ c.right ? __("right") : __("wrong") }}</span>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
// One run of the test set, case by case: a tick or a cross beside each case number, so right
// and wrong never rest on colour alone. Case numbers only; never a case's text. A run can hold the
// same case number twice, so each square is keyed by its place in the run, not by its number.
import { __ } from "@/translation";
import LucideCheck from "~icons/lucide/check";
import LucideX from "~icons/lucide/x";

defineProps<{ title: string; cases: { case: string; right: boolean }[] }>();
</script>

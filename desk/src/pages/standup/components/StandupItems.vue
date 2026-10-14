<template>
  <ul v-if="items.length" role="list" class="flex flex-col">
    <li
      v-for="(item, index) in items"
      :key="
        item.id || `${item.kind}:${item.reference_name || item.title}:${index}`
      "
      class="flex min-w-0 items-start gap-3 border-b border-outline-gray-1 py-2.5 last:border-b-0"
    >
      <component
        :is="KIND_ICONS[item.kind]"
        class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
        :aria-label="kindLabel(item.kind)"
      />
      <div class="min-w-0 flex-1">
        <NativeButton
          v-if="item.reference_doctype === 'Task'"
          class="text-left text-base text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
          @click="emit('open', item)"
        >
          {{ item.title }}
        </NativeButton>
        <RouterLink
          v-else-if="item.route"
          :to="item.route"
          class="text-base text-ink-gray-9 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
        >
          {{ item.title }}
        </RouterLink>
        <span v-else class="text-p-base text-ink-gray-9">{{ item.title }}</span>
        <p
          v-if="item.detail || item.helper_name || item.help_task"
          class="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-p-sm text-ink-gray-6"
        >
          <span v-if="item.detail">{{ item.detail }}</span>
          <span v-if="item.helper_name" class="inline-flex items-center gap-1">
            <LucideHandHelping class="size-3.5" aria-hidden="true" />
            {{ __("Help asked of {0}", item.helper_name) }}
          </span>
          <span v-if="item.help_task" class="inline-flex items-center gap-1">
            <LucideListPlus class="size-3.5" aria-hidden="true" />
            <span class="font-mono">{{ item.help_task }}</span>
          </span>
        </p>
        <slot name="actions" :item="item" :index="index" />
      </div>
      <Button
        v-if="removable"
        variant="ghost"
        class="!size-11 shrink-0"
        :aria-label="__('Remove {0}', item.title)"
        @click="emit('remove', index)"
      >
        <template #icon>
          <LucideX class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </li>
  </ul>
  <p v-else class="py-2.5 text-p-sm text-ink-gray-5">{{ empty }}</p>
</template>

<script setup lang="ts">
import NativeButton from "@/components/NativeButton";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { RouterLink } from "vue-router";
import LucideHandHelping from "~icons/lucide/hand-helping";
import LucideListChecks from "~icons/lucide/list-checks";
import LucideListOrdered from "~icons/lucide/list-ordered";
import LucideListPlus from "~icons/lucide/list-plus";
import LucideNewspaper from "~icons/lucide/newspaper";
import LucidePencilLine from "~icons/lucide/pencil-line";
import LucideTicket from "~icons/lucide/ticket";
import LucideX from "~icons/lucide/x";
import type { StandupItem } from "../standupMeta";

defineProps<{
  items: StandupItem[];
  /** shows a remove button on every row (the person's own draft) */
  removable?: boolean;
  /** what an empty section says */
  empty: string;
}>();

const emit = defineEmits<{
  remove: [index: number];
  /** a task row: the page opens it in place */
  open: [item: StandupItem];
}>();

const KIND_ICONS = {
  task: LucideListChecks,
  ticket: LucideTicket,
  post: LucideNewspaper,
  plan: LucideListOrdered,
  note: LucidePencilLine,
};

function kindLabel(kind: StandupItem["kind"]) {
  return {
    task: __("Task"),
    ticket: __("Ticket"),
    post: __("Content post"),
    plan: __("From your plan for today"),
    note: __("Your note"),
  }[kind];
}
</script>

<template>
  <SectionCard
    :title="__('Do next')"
    :description="__('In order: the most urgent first.')"
    :to="{ name: 'MyWork' }"
    :link-label="__('See all')"
  >
    <ol role="list">
      <li
        v-for="(item, index) in items"
        :key="itemKey(item)"
        class="relative flex items-center gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0 hover:bg-surface-gray-1 focus-within:bg-surface-gray-1"
      >
        <span
          class="w-5 shrink-0 text-right font-mono text-sm tabular-nums text-ink-gray-5"
          aria-hidden="true"
          >{{ index + 1 }}</span
        >
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 items-center gap-2">
            <RouterLink
              v-if="itemRoute(item)"
              :to="itemRoute(item)!"
              class="truncate rounded-sm text-base-medium text-ink-gray-9 after:absolute after:inset-0 after:content-[''] focus-visible:outline-none focus-visible:after:ring-2 focus-visible:after:ring-inset focus-visible:after:ring-highlight"
            >
              {{ item.title }}
            </RouterLink>
            <span v-else class="truncate text-base-medium text-ink-gray-9">
              {{ item.title }}
            </span>
            <KeyTag v-if="item.is_key" />
          </div>
          <p class="mt-0.5 truncate text-p-sm text-ink-gray-5">
            {{ item.kind === "ticket" ? __("Ticket") : __("Task") }}
            <template v-if="context(item)"> · {{ context(item) }}</template>
            ·
            <span class="font-mono text-xs tabular-nums">{{
              item.kind === "ticket" ? `#${item.name}` : item.name
            }}</span>
            <!-- the pill is hidden on phones, so the deadline moves here -->
            <span
              class="sm:hidden"
              :class="due(item).tone === 'danger' ? 'text-danger' : ''"
            >
              · {{ due(item).label }}</span
            >
          </p>
        </div>
        <span
          class="hidden shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium sm:inline-flex"
          :class="TONE_CLASSES[due(item).tone]"
        >
          <span class="size-1.5 rounded-full bg-current" aria-hidden="true" />
          {{ due(item).label }}
        </span>
        <div class="relative z-10 shrink-0">
          <Button
            v-if="stepFor(item)"
            size="sm"
            :label="stepFor(item)!.label"
            :loading="busy === item.name"
            :aria-label="`${stepFor(item)!.label}: ${item.title}`"
            @click="stepFor(item)!.run(item)"
          />
          <Button
            v-else-if="item.kind === 'ticket'"
            size="sm"
            :label="__('Reply')"
            :aria-label="`${__('Reply')}: ${item.title}`"
            :route="itemRoute(item) || undefined"
          />
          <Button
            v-else
            size="sm"
            :label="__('Open')"
            :aria-label="`${__('Open')}: ${item.title}`"
            :route="itemRoute(item) || undefined"
          />
        </div>
      </li>
    </ol>
  </SectionCard>

  <TaskDetailDialog
    v-model:task="detailTask"
    :action="detailAction"
    @changed="emit('changed')"
  />
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { TONE_CLASSES, type Tone } from "@/components/tone";
import KeyTag from "@/pages/work/components/KeyTag.vue";
import TaskDetailDialog from "@/pages/tasky/components/TaskDetailDialog.vue";
import {
  deadlineInfo,
  itemKey,
  itemRoute,
  type WorkItem,
} from "@/pages/work/workMeta";
import { __ } from "@/translation";
import { Button, dayjs } from "frappe-ui";
import { RouterLink } from "vue-router";
import type { DayTask } from "../homeMeta";
import { useDaySteps } from "../useDaySteps";

defineProps<{ items: DayTask[] }>();
const emit = defineEmits<{ changed: [] }>();

const { busy, detailTask, detailAction, stepFor } = useDaySteps(() =>
  emit("changed")
);

function context(item: WorkItem) {
  return item.kind === "ticket" ? item.customer : item.project_name;
}

/** The deadline as a pill: red when late, amber when today, else plain. */
function due(item: WorkItem): { label: string; tone: Tone } {
  const { label, overdue } = deadlineInfo(item);
  if (overdue) return { label, tone: "danger" };
  const today = item.deadline && dayjs(item.deadline).isSame(dayjs(), "day");
  return { label, tone: today ? "warning" : "neutral" };
}
</script>

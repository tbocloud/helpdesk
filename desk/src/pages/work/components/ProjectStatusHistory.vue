<template>
  <Dialog
    v-model:open="open"
    :title="__('History: {0}', project?.project_name ?? '')"
    size="lg"
  >
    <div class="flex max-h-[60vh] flex-col overflow-y-auto">
      <div v-if="history.loading && !history.data" :aria-label="__('Loading')">
        <div
          v-for="i in 3"
          :key="i"
          class="mb-3 h-16 animate-pulse rounded-md bg-surface-gray-2"
        />
      </div>
      <TaskyState
        v-else-if="history.error"
        :icon="LucideCircleAlert"
        :title="__('Couldn\'t load the history')"
        error
      >
        <Button :label="__('Retry')" @click="history.reload()" />
      </TaskyState>
      <TaskyState
        v-else-if="!items.length"
        :icon="LucideHistory"
        :title="__('No updates yet')"
        :message="__('Every update that is saved stays here.')"
      />
      <ol v-else class="flex flex-col" role="list">
        <li
          v-for="item in items"
          :key="item.name"
          class="border-b border-outline-gray-1 py-3 first:pt-0 last:border-b-0"
        >
          <div class="flex flex-wrap items-center gap-x-2 gap-y-1">
            <TaskyBadge :label="__(item.stage)" />
            <TaskyBadge
              v-if="item.waiting_on !== NOTHING"
              tone="warning"
              :icon="LucideHourglass"
              :label="__('Waiting on {0}', __(item.waiting_on))"
            />
            <span class="font-mono text-xs tabular-nums text-ink-gray-5">
              {{ dayjs(item.creation).format("D MMM YYYY") }}
            </span>
            <span class="text-xs text-ink-gray-5">
              {{ item.written_by_name }}
              <template v-if="item.source !== 'Manual'">
                · {{ __(item.source) }}
              </template>
            </span>
          </div>
          <ul
            v-if="lines(item.update_text).length"
            class="mt-1.5 list-disc pl-5 text-p-sm text-ink-gray-8"
          >
            <li v-for="line in lines(item.update_text)" :key="line">
              {{ line }}
            </li>
          </ul>
          <p v-if="item.next_step" class="mt-1 text-p-sm text-ink-gray-6">
            {{ __("Next") }}: {{ item.next_step }}
            <span v-if="item.next_step_date" class="font-mono tabular-nums">
              · {{ dayjs(item.next_step_date).format("D MMM YYYY") }}
            </span>
          </p>
        </li>
      </ol>
    </div>

    <template #actions="{ close }">
      <div class="flex justify-end">
        <Button :label="__('Close')" @click="close" />
      </div>
    </template>
  </Dialog>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { Button, createResource, Dialog, dayjs } from "frappe-ui";
import { computed, watch } from "vue";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideHistory from "~icons/lucide/history";
import LucideHourglass from "~icons/lucide/hourglass";
import { NOTHING, updateLines, type StatusRow } from "../projectStatusMeta";

interface HistoryItem {
  name: string;
  stage: string;
  waiting_on: string;
  update_text: string | null;
  next_step: string | null;
  next_step_date: string | null;
  written_by_name: string | null;
  source: string;
  creation: string;
}

const props = defineProps<{ project: StatusRow | null }>();
const open = defineModel<boolean>("open", { default: false });

const history = createResource({
  url: "helpdesk.api.project_status.get_status_history",
  makeParams: () => ({ project: props.project?.project }),
});

watch(open, (isOpen) => {
  if (!isOpen || !props.project) return;
  history.reset();
  history.fetch();
});

const items = computed<HistoryItem[]>(() => history.data ?? []);
const lines = (text: string | null) => updateLines({ update_text: text });
</script>

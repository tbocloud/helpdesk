<template>
  <SectionCard
    :title="__('Waiting for a person')"
    :description="
      __(
        'Fixes, corrections and releases waiting for their approval, the longest wait first. Open one to decide it where you always do.'
      )
    "
    :count="rows.length"
  >
    <ul v-if="rows.length" class="border-t border-outline-gray-1">
      <li
        v-for="row in rows"
        :key="row.name"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <a
          :href="row.link"
          class="flex flex-col gap-1 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 sm:flex-row sm:items-center sm:justify-between"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-1.5">
              <Badge :label="row.type" theme="blue" size="sm" />
              <Badge
                v-if="row.sensitive"
                :label="__('Senior')"
                theme="orange"
                size="sm"
              />
              <Badge
                v-if="row.risk"
                :label="__('Risk: {0}', row.risk)"
                :theme="row.risk === 'high' ? 'red' : 'gray'"
                size="sm"
              />
              <Badge
                v-if="row.escalated"
                :label="__('Escalated')"
                theme="red"
                size="sm"
              />
            </div>
            <div class="mt-1 truncate text-base text-ink-gray-9">
              <span v-if="row.ticket" class="font-mono text-ink-gray-6">
                #{{ row.ticket }}
              </span>
              {{ row.subject }}
            </div>
          </div>
          <div class="shrink-0 text-sm text-ink-gray-7 sm:text-right">
            <div>{{ row.assigned_name || __("Nobody yet") }}</div>
            <div class="text-ink-gray-5">
              {{ __("waited {0}", waited(row.waited_hours)) }}
              <template v-if="row.due_in_hours !== null">
                ·
                {{
                  row.due_in_hours > 0
                    ? __("escalates in {0}", waited(row.due_in_hours))
                    : __("past its escalation")
                }}
              </template>
              <template v-if="row.snoozed_until">
                · {{ __("snoozed until {0}", row.snoozed_until) }}
              </template>
            </div>
          </div>
        </a>
      </li>
    </ul>
    <p v-else-if="approvals.data" class="px-4 pb-4 text-sm text-ink-gray-5">
      {{ __("Nothing waits for an approval.") }}
    </p>
    <div
      v-else-if="approvals.loading"
      class="mx-4 mb-4 h-24 animate-pulse rounded-lg bg-surface-gray-1"
    />
    <ErrorMessage
      v-else-if="approvals.error"
      class="px-4 pb-4"
      :message="errorText(approvals.error)"
    />
  </SectionCard>
</template>

<script setup lang="ts">
import SectionCard from "@/components/SectionCard.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Badge, createResource, ErrorMessage } from "frappe-ui";
import { computed } from "vue";
import { BOARD_API, useBoardRefresh, waited } from "../boardMeta";

type Approval = {
  type: string;
  name: string;
  ticket: string;
  subject: string;
  assigned_name: string;
  waited_hours: number | null;
  due_in_hours: number | null;
  escalated: boolean;
  snoozed_until: string;
  risk: string;
  sensitive: boolean;
  link: string;
};

const approvals = createResource({
  url: `${BOARD_API}.approvals`,
  auto: true,
});
useBoardRefresh(approvals);
const rows = computed(() => (approvals.data as Approval[] | undefined) || []);
</script>

<template>
  <section
    v-if="options?.enabled"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-label="__('Proposals')"
  >
    <div
      class="flex items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 class="text-base-medium text-ink-gray-9">{{ __("Proposals") }}</h2>
      <Button
        v-if="canWrite"
        class="ml-auto"
        size="sm"
        :label="__('New proposal')"
        :route="{ name: 'LeadNewProposal', params: { leadId } }"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-if="!proposals.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{
        canWrite
          ? __("No proposals yet. Start one from the client's requirements.")
          : __("No proposals for this lead yet.")
      }}
    </p>
    <ul v-else role="list">
      <li
        v-for="p in proposals"
        :key="p.name"
        class="border-b border-outline-gray-1 last:border-b-0"
      >
        <router-link
          :to="{
            name: 'LeadProposal',
            params: { leadId, proposalId: p.name },
          }"
          class="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
        >
          <div class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="truncate text-base text-ink-gray-8" :title="p.title">{{
              p.title
            }}</span>
            <span class="text-xs tabular-nums text-ink-gray-6">
              {{ __("Version {0}", String(p.revision_no + 1)) }}
              <template v-if="p.view_count">
                · {{ __("{0} views", String(p.view_count)) }}
              </template>
            </span>
          </div>
          <TaskyBadge :label="__(p.status)" :tone="proposalTone(p.status)" />
        </router-link>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { Button } from "frappe-ui";
import { computed } from "vue";
import LucidePlus from "~icons/lucide/plus";
import {
  loadProposalOptions,
  proposalOptions,
  proposalTone,
  type ProposalOptions,
  type ProposalRow,
} from "./proposals";

defineProps<{
  leadId: string;
  proposals: ProposalRow[];
  canWrite: boolean;
}>();

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);
</script>

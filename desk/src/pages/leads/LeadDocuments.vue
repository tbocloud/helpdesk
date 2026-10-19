<template>
  <!-- the chain of client documents (TBO Smart's docs/client-documents.md): each made from
       the accepted one before it; the next action is the one primary button -->
  <section
    v-if="chain && chain.steps.length > 1"
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="titleId"
  >
    <div
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ __("Documents") }}
      </h2>
      <Button
        v-if="canWrite && chain.next"
        class="ml-auto"
        variant="solid"
        :label="chain.next.label"
        :loading="create.loading"
        @click="runNext"
      >
        <template #prefix>
          <component :is="nextIcon" class="size-4" aria-hidden="true" />
        </template>
      </Button>
      <p
        v-else-if="!chain.next"
        class="ml-auto flex items-center gap-1.5 text-sm text-success"
      >
        <LucideCircleCheck class="size-4" aria-hidden="true" />
        {{ __("Every document is accepted") }}
      </p>
    </div>
    <ol
      role="list"
      class="flex flex-col gap-2 p-3 sm:flex-row sm:flex-wrap sm:items-stretch"
    >
      <li
        v-for="(step, i) in chain.steps"
        :key="step.document_type"
        class="flex min-w-0 items-center gap-2 sm:flex-1"
      >
        <component
          :is="step.name ? 'router-link' : 'div'"
          :to="
            step.name
              ? {
                  name: 'LeadProposal',
                  params: { leadId, proposalId: step.name },
                }
              : undefined
          "
          :aria-current="isNext(step) ? 'step' : undefined"
          class="flex min-h-[44px] min-w-0 flex-1 items-center gap-2 rounded-lg border px-3 py-2"
          :class="[
            isNext(step)
              ? 'border-brand bg-brand-soft'
              : 'border-outline-gray-2',
            step.name
              ? 'hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight'
              : '',
          ]"
        >
          <LucideCircleCheck
            v-if="step.done"
            class="size-4 shrink-0 text-success"
            :aria-label="__('Done')"
          />
          <span
            v-else
            class="flex size-4 shrink-0 items-center justify-center font-mono text-xs tabular-nums text-ink-gray-5"
            aria-hidden="true"
            >{{ i + 1 }}</span
          >
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-sm font-medium text-ink-gray-8">{{
              step.label
            }}</span>
            <span
              v-if="step.quotation_status && !step.done"
              class="truncate text-xs text-ink-gray-6"
              >{{ __("Price: {0}", __(step.quotation_status)) }}</span
            >
          </span>
          <TaskyBadge
            :label="step.status_label || __('Not started')"
            :tone="step.status ? proposalTone(step.status) : 'neutral'"
          />
        </component>
        <LucideChevronRight
          v-if="i < chain.steps.length - 1"
          class="hidden size-4 shrink-0 text-ink-gray-4 sm:block"
          aria-hidden="true"
        />
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, toast } from "frappe-ui";
import { computed, useId } from "vue";
import { useRouter } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucidePlus from "~icons/lucide/plus";
import {
  proposalTone,
  type DocumentChain,
  type DocumentStep,
  type Proposal,
} from "./proposals";

const props = defineProps<{
  leadId: string;
  chain?: DocumentChain | null;
  canWrite: boolean;
}>();
const router = useRouter();
const titleId = `lead-documents-${useId()}`;

const nextIcon = computed(() =>
  props.chain?.next?.action === "open" ? LucideArrowRight : LucidePlus
);

function isNext(step: DocumentStep) {
  return props.chain?.next?.document_type === step.document_type;
}

function open(name: string) {
  router.push({
    name: "LeadProposal",
    params: { leadId: props.leadId, proposalId: name },
  });
}

const create = createResource({
  url: "helpdesk.api.proposals.create_document",
  method: "POST",
  onSuccess(d: { proposal: Proposal; warnings: string[] }) {
    for (const warning of d.warnings ?? []) toast.warning(warning);
    toast.success(__("{0} created", d.proposal.document_label));
    open(d.proposal.name);
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't create it. Try again.")));
  },
});

function runNext() {
  const next = props.chain?.next;
  if (!next || create.loading) return;
  if (next.action === "create_proposal")
    router.push({ name: "LeadNewProposal", params: { leadId: props.leadId } });
  else if (next.action === "open" && next.name) open(next.name);
  else if (next.action === "create")
    create.submit({ source: next.source, document_type: next.document_type });
}
</script>

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
        @click="openNew"
      >
        <template #prefix>
          <LucidePlus class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </div>
    <p v-if="!proposals.length" class="px-4 py-4 text-p-sm text-ink-gray-6">
      {{
        canWrite
          ? __("No proposals yet. Start one from a template.")
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

    <Dialog v-model:open="showNew" :title="__('New proposal')" size="lg">
      <form
        :id="formId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="create"
      >
        <fieldset class="flex flex-col gap-1">
          <legend class="mb-2 text-p-sm text-ink-gray-6">
            {{ __("Start from") }}
          </legend>
          <label
            v-for="t in templateChoices"
            :key="t.value"
            class="flex min-h-[44px] cursor-pointer items-start gap-3 rounded-md px-2 py-2 hover:bg-surface-gray-1"
          >
            <input
              v-model="template"
              type="radio"
              name="proposal-template"
              :value="t.value"
              class="mt-1 size-4 border-outline-gray-4 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-highlight"
            />
            <span class="flex flex-col">
              <span class="text-base text-ink-gray-8">{{ t.label }}</span>
              <span v-if="t.description" class="text-p-sm text-ink-gray-6">{{
                t.description
              }}</span>
            </span>
          </label>
        </fieldset>
        <label
          v-if="options?.ai"
          class="flex min-h-[44px] cursor-pointer items-start gap-3 rounded-md border border-outline-gray-2 px-3 py-2"
        >
          <input
            v-model="aiDraft"
            type="checkbox"
            class="mt-1 size-4 rounded border-outline-gray-4 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-highlight"
          />
          <span class="flex flex-col">
            <span class="text-base text-ink-gray-8">{{
              __("Draft it with AI")
            }}</span>
            <span class="text-p-sm text-ink-gray-6">{{
              __(
                "Writes each block from the lead, its notes and its meetings' minutes. You read and edit everything before sending."
              )
            }}</span>
          </span>
        </label>
        <p v-if="error" role="alert" class="text-p-sm text-danger">
          {{ error }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="formId"
            :label="aiDraft ? __('Draft proposal') : __('Create proposal')"
            :loading="createResourceState.loading"
          />
        </div>
      </template>
    </Dialog>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, Dialog, toast } from "frappe-ui";
import { computed, ref, useId } from "vue";
import { useRouter } from "vue-router";
import LucidePlus from "~icons/lucide/plus";
import {
  proposalOptions,
  proposalTone,
  type Proposal,
  type ProposalOptions,
  type ProposalRow,
} from "./proposals";

const props = defineProps<{
  leadId: string;
  proposals: ProposalRow[];
  canWrite: boolean;
}>();

const router = useRouter();
const formId = `new-proposal-${useId()}`;

if (!proposalOptions.data && !proposalOptions.loading) proposalOptions.fetch();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);

const templateChoices = computed(() => [
  ...(options.value?.templates ?? [])
    .filter((t) => t.enabled)
    .map((t) => ({
      value: t.name,
      label: t.template_name,
      description: t.description,
    })),
  {
    value: "",
    label: __("Blank"),
    description: __("Cover, solution, pricing and terms, all empty."),
  },
]);

const showNew = ref(false);
const template = ref("");
const aiDraft = ref(false);
const error = ref("");

function openNew() {
  template.value = templateChoices.value[0]?.value ?? "";
  aiDraft.value = false;
  error.value = "";
  showNew.value = true;
}

const createResourceState = createResource({
  url: "helpdesk.api.proposals.create_proposal",
  method: "POST",
  onSuccess(data: { proposal: Proposal; warnings: string[] }) {
    showNew.value = false;
    for (const warning of data.warnings ?? []) toast.warning(warning);
    router.push({
      name: "LeadProposal",
      params: { leadId: props.leadId, proposalId: data.proposal.name },
    });
  },
  onError(e: unknown) {
    error.value = errorText(
      e,
      __("Couldn't create the proposal. Check your connection and try again.")
    );
  },
});

function create() {
  if (createResourceState.loading) return;
  error.value = "";
  createResourceState.submit({
    lead: props.leadId,
    template: template.value || null,
    ai_draft: aiDraft.value ? 1 : 0,
  });
}
</script>

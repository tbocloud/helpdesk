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
      <!-- the UAT sign-off, sent and followed from here (docs/project-signoff.md, From the lead) -->
      <template v-if="chain.next?.action === 'uat' && uat.data?.project">
        <Button
          v-if="!uat.data.signoff && uat.data.can_send"
          class="ml-auto"
          variant="solid"
          :label="__('Send for sign-off')"
          @click="showSend = true"
        >
          <template #prefix>
            <LucideSend class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          v-else-if="uat.data.signoff && uat.data.can_open"
          class="ml-auto"
          variant="solid"
          :label="__('Open sign-off')"
          :route="{
            name: 'TaskySignoff',
            params: {
              projectId: uat.data.project,
              signoffId: uat.data.signoff.name,
            },
          }"
        >
          <template #prefix>
            <LucideArrowRight class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <p v-else class="ml-auto text-sm text-ink-gray-6">
          {{
            uat.data.signoff
              ? __("UAT sign-off: {0}", uatLabel)
              : __("The project team sends the UAT sign-off")
          }}
        </p>
      </template>
      <Button
        v-else-if="canWrite && chain.next && !deliveryStep(chain.next.action)"
        class="ml-auto"
        variant="solid"
        :label="chain.next.label"
        :loading="busy"
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
      <p
        v-else-if="deliveryStep(chain.next.action)"
        class="ml-auto text-sm text-ink-gray-6"
      >
        {{ __("The project team takes it from here") }}
      </p>
    </div>
    <!-- a grid, so the whole chain fits on one line on a wide screen and wraps on a narrow one -->
    <ol
      role="list"
      class="grid grid-cols-1 gap-2 p-3 sm:grid-cols-3 lg:grid-cols-[repeat(auto-fit,minmax(9rem,1fr))]"
    >
      <li
        v-for="(step, i) in chain.steps"
        :key="step.document_type"
        class="flex min-w-0"
      >
        <component
          :is="opens(step) ? 'router-link' : 'div'"
          :to="opens(step) ? stepRoute(step) : undefined"
          :aria-current="isNext(step) ? 'step' : undefined"
          class="flex min-h-[44px] min-w-0 flex-1 flex-col gap-1.5 rounded-lg border px-3 py-2"
          :class="[
            isNext(step)
              ? 'border-brand bg-brand-soft'
              : 'border-outline-gray-2',
            opens(step)
              ? 'hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight'
              : '',
          ]"
        >
          <span class="flex min-w-0 items-center gap-1.5">
            <LucideCircleCheck
              v-if="step.done || (step.document_type === 'UAT' && uatSigned)"
              class="size-4 shrink-0 text-success"
              :aria-label="__('Done')"
            />
            <span
              v-else
              class="flex size-4 shrink-0 items-center justify-center font-mono text-xs tabular-nums text-ink-gray-5"
              aria-hidden="true"
              >{{ i + 1 }}</span
            >
            <span
              class="truncate text-sm font-medium text-ink-gray-8"
              :title="step.label"
              >{{ step.label }}</span
            >
          </span>
          <span
            v-if="step.document_type === 'UAT' && uat.data?.signoff"
            class="flex min-w-0 flex-col gap-1"
          >
            <TaskyBadge
              :label="uatLabel"
              :tone="uatMeta.tone"
              :icon="uatMeta.icon"
              class="self-start"
            />
            <span
              v-if="uatSigned"
              class="truncate text-xs text-ink-gray-6"
              :title="uatSigner"
              >{{ uatSigner }}</span
            >
            <a
              v-if="uatSigned && uat.data.signoff.has_pdf"
              :href="pdfUrl"
              class="inline-flex min-h-[24px] items-center gap-1 self-start rounded text-xs font-medium text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
              @click.stop
            >
              <LucideDownload class="size-3.5" aria-hidden="true" />
              {{ __("Signed PDF") }}
            </a>
          </span>
          <span v-else class="flex min-w-0 flex-wrap items-center gap-1.5">
            <TaskyBadge
              :label="step.status_label || __('Not started')"
              :tone="step.status ? proposalTone(step.status) : 'neutral'"
            />
            <span
              v-if="step.quotation_status && !step.done"
              class="truncate text-xs text-ink-gray-6"
              >{{ __("Price: {0}", __(step.quotation_status)) }}</span
            >
          </span>
        </component>
      </li>
    </ol>
  </section>
  <SignoffFormDialog
    v-if="uat.data?.project && uat.data.can_send"
    v-model:open="showSend"
    :project-id="uat.data.project"
    uat
    :lead="leadId"
    @saved="uat.reload()"
  />
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import SignoffFormDialog from "@/pages/tasky/components/SignoffFormDialog.vue";
import { signoffStatusMeta } from "@/pages/tasky/signoffMeta";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import { Button, createResource, toast } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideDownload from "~icons/lucide/download";
import LucidePlus from "~icons/lucide/plus";
import LucideSend from "~icons/lucide/send";
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
const authStore = useAuthStore();
const titleId = `lead-documents-${useId()}`;

// a Sales Employee's chain stops at the client documents: the project and its UAT
// belong to the project team, whose pages they don't open (docs/departments.md)
const DELIVERY_TYPES = new Set(["Project", "UAT"]);
const DELIVERY_ACTIONS = new Set(["create_project", "uat"]);

function deliveryStep(action?: string) {
  return authStore.isSalesEmployee && DELIVERY_ACTIONS.has(action || "");
}

function opens(step: DocumentStep) {
  // the UAT step holds its own Signed PDF link once the hub has its sign-off, and the
  // header's Open sign-off opens it
  if (step.document_type === "UAT" && uat.data?.signoff) return false;
  return (
    !!step.name &&
    !(authStore.isSalesEmployee && DELIVERY_TYPES.has(step.document_type))
  );
}

const nextIcon = computed(() =>
  ["open", "uat"].includes(props.chain?.next?.action || "")
    ? LucideArrowRight
    : LucidePlus
);

/** A document opens in the builder; the project on its page, the UAT on its sign-off tab. */
function stepRoute(step: DocumentStep) {
  if (step.document_type === "Project")
    return { name: "TaskyProject", params: { projectId: step.name } };
  if (step.document_type === "UAT")
    return { name: "TaskySignoffs", params: { projectId: step.name } };
  return {
    name: "LeadProposal",
    params: { leadId: props.leadId, proposalId: step.name },
  };
}

// ---------- the UAT sign-off, from the hub (helpdesk.api.project_signoff.get_lead_signoff) ----------

interface LeadSignoff {
  project: string | null;
  signoff: null | {
    name: string;
    status: string;
    /** Sent turns Viewed once the client opened the link with their code */
    customer_status: string;
    signer_name?: string | null;
    signer_designation?: string | null;
    has_pdf: boolean;
  };
  can_send: boolean;
  can_open: boolean;
}

const hasUatStep = computed(
  () => !!props.chain?.steps.some((s) => s.document_type === "UAT" && !!s.name)
);
const uat = createResource<LeadSignoff>({
  url: "helpdesk.api.project_signoff.get_lead_signoff",
  makeParams: () => ({ lead: props.leadId }),
  onError() {},
});
watch(
  () => [props.leadId, hasUatStep.value],
  () => hasUatStep.value && uat.reload(),
  { immediate: true }
);

const uatStatus = computed(() => uat.data?.signoff?.customer_status || "");
const uatMeta = computed(() => signoffStatusMeta(uatStatus.value));
const uatLabel = computed(() => __(uatMeta.value.label));
const uatSigned = computed(() => uat.data?.signoff?.status === "Signed");
const uatSigner = computed(() => {
  const s = uat.data?.signoff;
  return s?.signer_name
    ? __("By {0}, {1}", s.signer_name, s.signer_designation || "")
    : "";
});
const pdfUrl = computed(
  () =>
    `/api/method/helpdesk.api.project_signoff.download_lead_signoff_pdf?lead=${encodeURIComponent(
      props.leadId
    )}`
);
const showSend = ref(false);

// live while the lead is on screen: the client answers and signs on their side
const LIVE_EVERY = 30_000;
const visibility = useDocumentVisibility();
useIntervalFn(() => {
  if (
    visibility.value === "visible" &&
    uat.data?.signoff &&
    !uatSigned.value &&
    !uat.loading
  )
    uat.reload();
}, LIVE_EVERY);

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

const createProject = createResource({
  url: "helpdesk.api.proposals.create_project_from_plan",
  method: "POST",
  onSuccess(d: { project: string }) {
    toast.success(__("Project {0} created from the plan", d.project));
    router.push({ name: "TaskyProject", params: { projectId: d.project } });
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't create the project. Try again.")));
  },
});

const createProposalProject = createResource({
  url: "helpdesk.api.proposals.create_project_from_proposal",
  method: "POST",
  onSuccess(d: { project: string }) {
    toast.success(__("Project {0} created from the proposal", d.project));
    router.push({ name: "TaskyProject", params: { projectId: d.project } });
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't create the project. Try again.")));
  },
});

const busy = computed(
  () => create.loading || createProject.loading || createProposalProject.loading
);

function runNext() {
  const next = props.chain?.next;
  if (!next || busy.value) return;
  if (next.action === "create_proposal")
    router.push({ name: "LeadNewProposal", params: { leadId: props.leadId } });
  else if (next.action === "open" && next.name) open(next.name);
  else if (next.action === "create")
    create.submit({ source: next.source, document_type: next.document_type });
  else if (next.action === "create_project" && next.source_type === "Proposal")
    createProposalProject.submit({ proposal: next.source });
  else if (next.action === "create_project")
    createProject.submit({ plan: next.source });
  else if (next.action === "uat" && next.name)
    router.push({ name: "TaskySignoffs", params: { projectId: next.name } });
}
</script>

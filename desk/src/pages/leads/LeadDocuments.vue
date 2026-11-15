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
      <!-- a lost lead: nothing moves, and it says why -->
      <p
        v-if="chain.blocked"
        class="ml-auto flex items-center gap-1.5 text-sm text-ink-gray-6"
      >
        <LucideLock class="size-4 shrink-0" aria-hidden="true" />
        {{ chain.blocked }}
      </p>
      <!-- the UAT sign-off, sent and followed from here (docs/project-signoff.md, From the lead) -->
      <template v-else-if="chain.next?.action === 'uat' && uat.data?.project">
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
        v-else-if="!chain.next && !chain.note"
        class="ml-auto flex items-center gap-1.5 text-sm text-success"
      >
        <LucideCircleCheck class="size-4" aria-hidden="true" />
        {{
          anySkipped
            ? __("Every step is done or skipped")
            : __("Every document is accepted")
        }}
      </p>
      <p v-else-if="!chain.next" class="ml-auto text-sm text-ink-gray-6">
        {{ chain.note }}
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
        class="relative flex min-w-0"
      >
        <component
          :is="opens(step) ? 'router-link' : 'div'"
          :to="opens(step) ? stepRoute(step) : undefined"
          :aria-current="isNext(step) ? 'step' : undefined"
          class="flex min-h-[44px] min-w-0 flex-1 flex-col gap-1.5 rounded-lg border px-3 py-2"
          :class="[
            menuFor(step).length ? 'pr-12 sm:pr-10' : '',
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
            <LucideCircleMinus
              v-else-if="step.skipped || step.implicit"
              class="size-4 shrink-0 text-ink-gray-5"
              :aria-label="step.status_label || __('Skipped')"
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
          <!-- skipped or not used: gray, with who, when and why -->
          <span
            v-else-if="step.skipped || step.implicit"
            class="flex min-w-0 flex-col gap-1"
          >
            <TaskyBadge
              :label="step.status_label || __('Skipped')"
              tone="neutral"
              class="self-start"
            />
            <span
              v-if="step.skipped"
              class="truncate text-xs text-ink-gray-6"
              :title="step.skipped.reason"
            >
              {{
                __(
                  "{0}, {1}: {2}",
                  step.skipped.by_name || step.skipped.by,
                  shortDate(step.skipped.on),
                  step.skipped.reason
                )
              }}
            </span>
          </span>
          <span v-else class="flex min-w-0 flex-wrap items-center gap-1.5">
            <TaskyBadge
              :label="step.status_label || __('Not started')"
              :tone="
                step.status ? proposalTone(step.status as ProposalStatus) : 'neutral'
              "
            />
            <span
              v-if="step.quotation_status && !step.done"
              class="truncate text-xs text-ink-gray-6"
              >{{ __("Price: {0}", __(step.quotation_status)) }}</span
            >
          </span>
        </component>
        <!-- beside the card, not in it: a link can't hold a button -->
        <Dropdown
          v-if="menuFor(step).length"
          :options="menuFor(step)"
          class="absolute right-1 top-1"
        >
          <Button
            variant="ghost"
            class="size-11 sm:size-8"
            :aria-label="__('More for {0}', step.label)"
          >
            <template #icon>
              <LucideEllipsis class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
      </li>
    </ol>
    <!-- a chain started further on: the steps before it, marked not used in one go -->
    <div
      v-if="chain.can_steer && unusedSteps.length"
      class="flex flex-wrap items-center gap-2 border-t border-outline-gray-1 px-4 py-2"
    >
      <p class="text-p-sm text-ink-gray-6">
        {{
          __(
            "{0} weren't used: the documents started further on.",
            unusedSteps.map((s) => s.label).join(", ")
          )
        }}
      </p>
      <Button
        variant="subtle"
        class="ml-auto"
        :label="__('Mark them not used')"
        @click="askSkip(unusedSteps, 'Not used')"
      />
    </div>
    <!-- skip one step, or mark earlier ones not used: a short reason is required -->
    <Dialog
      :open="skipping.open"
      size="md"
      :title="skipping.title"
      @update:open="(value: boolean) => !value && closeSkip()"
    >
      <form class="flex flex-col gap-4" @submit.prevent="confirmSkip">
        <p class="text-p-sm text-ink-gray-7">{{ skipping.text }}</p>
        <FormControl
          v-model="skipping.reason"
          type="textarea"
          :label="__('Why? (required)')"
          :placeholder="__('e.g. Repeat client, the scope is already agreed')"
          :rows="2"
          maxlength="500"
          required
        />
        <ErrorMessage
          v-if="skipping.error"
          :message="skipping.error"
          role="alert"
        />
        <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            :label="__('Cancel')"
            :disabled="skip.loading"
            @click="closeSkip"
          />
          <Button
            type="submit"
            variant="solid"
            :label="skipping.confirm"
            :loading="skip.loading"
            :disabled="!skipping.reason.trim()"
          />
        </div>
      </form>
    </Dialog>
    <!-- inside the one root, so the page's grid class (col-span) reaches the section -->
    <SignoffFormDialog
      v-if="uat.data?.project && uat.data.can_send"
      v-model:open="showSend"
      :project-id="uat.data.project"
      uat
      :lead="leadId"
      @saved="uat.reload()"
    />
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { shortDate } from "@/pages/tasky/taskMeta";
import { useAuthStore } from "@/stores/auth";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import SignoffFormDialog from "@/pages/tasky/components/SignoffFormDialog.vue";
import { signoffStatusMeta } from "@/pages/tasky/signoffMeta";
import { useDocumentVisibility, useIntervalFn } from "@vueuse/core";
import {
  Button,
  createResource,
  Dialog,
  Dropdown,
  ErrorMessage,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideCircleMinus from "~icons/lucide/circle-minus";
import LucideEllipsis from "~icons/lucide/ellipsis";
import LucideLock from "~icons/lucide/lock";
import LucideDownload from "~icons/lucide/download";
import LucidePlus from "~icons/lucide/plus";
import LucideSend from "~icons/lucide/send";
import {
  proposalTone,
  type DocumentChain,
  type DocumentStep,
  type Proposal,
  type ProposalStatus,
  type StepSkipStatus,
} from "./proposals";

const props = defineProps<{
  leadId: string;
  chain?: DocumentChain | null;
  canWrite: boolean;
}>();
const emit = defineEmits<{
  /** a step skipped or brought back: the lead's chain is read again */
  changed: [];
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
const uatSigned = computed(() => uat.data?.signoff?.status === "Signed Off");
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

const createLeadProject = createResource({
  url: "helpdesk.api.proposals.create_project_from_lead",
  method: "POST",
  onSuccess(d: { project: string }) {
    toast.success(__("Project {0} created", d.project));
    router.push({ name: "TaskyProject", params: { projectId: d.project } });
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't create the project. Try again.")));
  },
});

const busy = computed(
  () =>
    create.loading ||
    createProject.loading ||
    createProposalProject.loading ||
    createLeadProject.loading
);

// ---------- a flexible chain: make a step out of order, skip one, bring one back ----------

const anySkipped = computed(
  () => !!props.chain?.steps.some((s) => s.skipped || s.implicit)
);
/** shown Not used because the chain started further on, not marked yet */
const unusedSteps = computed(
  () =>
    props.chain?.steps.filter(
      (s) => s.implicit && s.actions?.includes("skip")
    ) ?? []
);

function isDelivery(step: DocumentStep) {
  return DELIVERY_TYPES.has(step.document_type);
}

/** Make this step now: in its place in the chain, or out of order (the ERP site says who may). */
function createStep(step: DocumentStep) {
  if (busy.value) return;
  const next = props.chain?.next;
  if (next?.document_type === step.document_type) return runNext();
  if (step.document_type === "Proposal")
    router.push({ name: "LeadNewProposal", params: { leadId: props.leadId } });
  else if (step.document_type === "Project")
    createLeadProject.submit({ lead: props.leadId });
  else createDocument(step.document_type, step.source);
}

function menuFor(step: DocumentStep) {
  if (props.chain?.blocked || !props.canWrite) return [];
  if (authStore.isSalesEmployee && isDelivery(step)) return [];
  const actions = step.actions ?? [];
  const options = [];
  if (actions.includes("create") && !isNext(step))
    options.push({
      label:
        step.document_type === "Proposal"
          ? __("New proposal")
          : __("Create {0}", step.label),
      icon: "plus",
      onClick: () => createStep(step),
    });
  if (actions.includes("skip"))
    options.push({
      label: __("Skip…"),
      icon: "skip-forward",
      onClick: () => askSkip([step], "Skipped"),
    });
  if (actions.includes("bring_back"))
    options.push({
      label: __("Bring back"),
      icon: "rotate-ccw",
      onClick: () =>
        bringBack.submit({
          lead: props.leadId,
          document_type: step.document_type,
        }),
    });
  return options;
}

/** The step that opens once these are skipped: the first after them still to do. */
function stepAfter(skipped: DocumentStep[]) {
  const steps = props.chain?.steps ?? [];
  const last = Math.max(...skipped.map((s) => steps.indexOf(s)));
  return steps
    .slice(last + 1)
    .find((s) => !s.done && !s.skipped && !s.implicit);
}

const skipping = reactive({
  open: false,
  steps: [] as DocumentStep[],
  status: "Skipped" as StepSkipStatus,
  title: "",
  text: "",
  confirm: "",
  reason: "",
  error: "",
});

function askSkip(steps: DocumentStep[], status: StepSkipStatus) {
  const after = stepAfter(steps);
  const names = steps.map((s) => s.label).join(", ");
  Object.assign(skipping, {
    open: true,
    steps,
    status,
    reason: "",
    error: "",
    title:
      status === "Skipped"
        ? __("Skip {0}?", names)
        : __("Mark {0} not used?", names),
    text:
      status === "Skipped"
        ? after
          ? __(
              "The next step, {0}, opens. You can bring {1} back later.",
              after.label,
              names
            )
          : __(
              "Nothing after it is left to do. You can bring {0} back later.",
              names
            )
        : __(
            "They show as Not used, with your reason, on the lead and in reports."
          ),
    confirm: status === "Skipped" ? __("Skip {0}", names) : __("Mark not used"),
  });
}

function closeSkip() {
  if (!skip.loading) skipping.open = false;
}

const skip = createResource({
  url: "helpdesk.api.proposals.skip_steps",
  method: "POST",
  onSuccess() {
    toast.success(
      skipping.status === "Skipped"
        ? __("{0} skipped", skipping.steps.map((s) => s.label).join(", "))
        : __("Marked not used")
    );
    skipping.open = false;
    emit("changed");
  },
  onError(e: unknown) {
    skipping.error = errorText(e, __("Couldn't skip it. Try again."));
  },
});

function confirmSkip() {
  const reason = skipping.reason.trim();
  if (!reason || skip.loading) return;
  skipping.error = "";
  skip.submit({
    lead: props.leadId,
    document_types: JSON.stringify(skipping.steps.map((s) => s.document_type)),
    reason,
    status: skipping.status,
  });
}

const bringBack = createResource({
  url: "helpdesk.api.proposals.bring_back_step",
  method: "POST",
  onSuccess() {
    toast.success(__("Brought back"));
    emit("changed");
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't bring it back. Try again.")));
  },
});

/** Made from its accepted source, or from the lead when there is none. */
function createDocument(documentType: string, source?: string | null) {
  create.submit(
    source
      ? { source, document_type: documentType }
      : { lead: props.leadId, document_type: documentType }
  );
}

function runNext() {
  const next = props.chain?.next;
  if (!next || busy.value) return;
  if (next.action === "create_proposal")
    router.push({ name: "LeadNewProposal", params: { leadId: props.leadId } });
  else if (next.action === "open" && next.name) open(next.name);
  else if (next.action === "create")
    createDocument(next.document_type, next.source);
  else if (next.action === "create_project" && next.source_type === "Proposal")
    createProposalProject.submit({ proposal: next.source });
  else if (next.action === "create_project" && next.source_type === "Lead")
    createLeadProject.submit({ lead: props.leadId });
  else if (next.action === "create_project")
    createProject.submit({ plan: next.source });
  else if (next.action === "uat" && next.name)
    router.push({ name: "TaskySignoffs", params: { projectId: next.name } });
}
</script>

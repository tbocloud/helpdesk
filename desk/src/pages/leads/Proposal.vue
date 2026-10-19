<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'Leads' }"
            class="hidden shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4 sm:inline"
            >{{ __("Leads") }}</router-link
          >
          <LucideChevronRight
            class="hidden size-4 shrink-0 text-ink-gray-4 sm:inline"
            aria-hidden="true"
          />
          <router-link
            :to="{ name: 'Lead', params: { leadId } }"
            class="min-w-0 shrink truncate rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >{{ proposal?.lead_name || leadId }}</router-link
          >
          <LucideChevronRight
            class="hidden size-4 shrink-0 text-ink-gray-4 sm:inline"
            aria-hidden="true"
          />
          <h1 class="sr-only truncate text-ink-gray-9 sm:not-sr-only">
            {{ proposal?.title || proposalId }}
          </h1>
        </nav>
      </template>
      <template v-if="proposal" #right-header>
        <TaskyBadge
          class="hidden sm:inline-flex"
          :label="__(proposal.status)"
          :tone="proposalTone(proposal.status)"
        />
        <Dropdown :options="shareOptions">
          <Button :label="__('Share')">
            <template #prefix>
              <LucideShare2 class="size-4" aria-hidden="true" />
            </template>
          </Button>
        </Dropdown>
        <Button
          v-if="isDraft && proposal.can_write"
          :label="dirty ? __('Save changes') : __('Saved')"
          :disabled="!dirty"
          :loading="saveResource.loading"
          @click="save"
        />
        <Button
          v-else-if="proposal.can_write && proposal.is_latest"
          :label="isMobileView ? __('Revise') : __('Create revision')"
          :loading="revisionResource.loading"
          @click="revisionResource.submit({ name: proposalId })"
        />
        <Button
          v-if="proposal.can_write && canSendStatus"
          variant="solid"
          :label="proposal.status === 'Draft' ? __('Send') : __('Send again')"
          :disabled="!!proposal.send_blockers.length || dirty"
          :tooltip="sendTooltip"
          @click="openSend"
        >
          <template #prefix>
            <LucideSend class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="detail.error && !proposal"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the proposal')"
          :message="
            errorText(detail.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Try again')" @click="detail.reload()" />
          <Button
            :label="__('Back to the lead')"
            :route="{ name: 'Lead', params: { leadId } }"
          />
        </TaskyState>

        <div
          v-else-if="!proposal"
          class="grid grid-cols-1 gap-4 xl:grid-cols-2"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            class="h-96 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          />
          <div
            class="h-96 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          />
        </div>

        <div v-else class="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div class="flex min-w-0 flex-col gap-4">
            <!-- why Send is off, in the ERP site's words -->
            <div
              v-if="
                proposal.can_write &&
                canSendStatus &&
                proposal.send_blockers.length
              "
              role="status"
              class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-p-sm text-warning"
            >
              <LucideTriangleAlert
                class="mt-0.5 size-4 shrink-0"
                aria-hidden="true"
              />
              <div class="flex flex-col gap-1">
                <span class="font-medium">{{ __("Can't send yet") }}</span>
                <span v-for="(reason, i) in proposal.send_blockers" :key="i">{{
                  reason
                }}</span>
              </div>
            </div>
            <p
              v-if="!isDraft"
              class="rounded-lg border border-outline-gray-2 bg-surface-gray-1 px-3 py-2 text-p-sm text-ink-gray-7"
            >
              {{
                proposal.is_latest
                  ? __(
                      "This version went to the client and can't change. Create a revision to edit it; the client keeps this one until you send the new one."
                    )
                  : __("A newer version of this proposal exists.")
              }}
            </p>

            <ProposalTracking :proposal="proposal" />

            <section
              class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-label="__('Details')"
            >
              <FormControl
                v-model="form.title"
                :label="__('Title')"
                maxlength="140"
                :disabled="!editable"
              />
              <div class="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <FormControl
                  v-model="form.valid_till"
                  type="date"
                  :label="__('Valid till')"
                  :disabled="!editable"
                />
                <div class="flex flex-col gap-1.5">
                  <span :id="priceLabelId" class="text-xs text-ink-gray-5">{{
                    __("Price shown")
                  }}</span>
                  <TabButtons
                    :model-value="form.pricing_mode"
                    :aria-labelledby="priceLabelId"
                    :options="pricingModeOptions"
                    @update:model-value="
                      editable && (form.pricing_mode = $event)
                    "
                  />
                </div>
              </div>
              <FormControl
                v-if="letterHeadOptions.length > 1"
                v-model="form.letter_head"
                type="select"
                :label="__('Letter head')"
                :options="letterHeadOptions"
                :disabled="!editable"
              />
              <p
                v-else-if="options?.enabled && options?.can_edit_templates"
                role="status"
                class="flex items-start gap-2 rounded-lg bg-warning-soft px-3 py-2 text-p-sm text-warning"
              >
                <LucideTriangleAlert
                  class="mt-0.5 size-4 shrink-0"
                  aria-hidden="true"
                />
                {{
                  __(
                    "The ERP site has no Letter Head yet, so proposals show only the company's logo. Add one there (Letter Head) and mark it default."
                  )
                }}
              </p>
              <p class="text-p-sm tabular-nums text-ink-gray-6">
                {{ __("About {0} pages", String(pages)) }}
                <template v-if="proposal.page_guide">
                  · {{ __("guide: {0}", proposal.page_guide) }}</template
                >
              </p>
              <p
                v-if="proposal.ai"
                class="text-p-sm tabular-nums text-ink-gray-6"
              >
                {{
                  __(
                    "AI on this proposal: {0} runs, {1} tokens, about ${2}",
                    String(proposal.ai.runs),
                    (
                      proposal.ai.input_tokens + proposal.ai.output_tokens
                    ).toLocaleString(),
                    proposal.ai.cost_usd.toFixed(3)
                  )
                }}
                <template v-if="proposal.ai.estimate_tokens">
                  ·
                  {{
                    __(
                      "a full regenerate is about {0} tokens",
                      proposal.ai.estimate_tokens.toLocaleString()
                    )
                  }}</template
                >
              </p>
            </section>

            <ProposalAssistant
              :proposal="proposalId"
              :chat="proposal.chat || []"
              :ai="!!options?.ai"
              :editable="editable"
              :dirty="dirty"
              @changed="setProposal"
            />

            <details
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
            >
              <summary
                class="flex min-h-[44px] cursor-pointer items-center px-4 text-base-medium text-ink-gray-9"
              >
                {{ __("Client, requirements and scoping") }}
              </summary>
              <div
                class="flex flex-col gap-5 border-t border-outline-gray-1 p-4"
              >
                <ClientProfileForm
                  v-model="form.client_profile"
                  :lead="leadId"
                  :can-read="!!options?.ai"
                  :disabled="!editable"
                />
                <FormControl
                  v-model="form.requirements"
                  type="textarea"
                  :rows="4"
                  :label="__('Customer requirements')"
                  maxlength="8000"
                  :disabled="!editable"
                />
                <ProposalScopingForm
                  v-model="form.scoping"
                  :questions="template?.questions"
                  :catalogue="options?.catalogue || []"
                  :solution-type="proposal.solution_type"
                  :hosting="options?.hosting || []"
                  :disabled="!editable"
                />
                <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <FormControl
                    :model-value="form.scoping.timeline_template || ''"
                    type="select"
                    :label="__('Timeline')"
                    :options="timelineOptions"
                    :disabled="!editable"
                    @update:model-value="
                      form.scoping.timeline_template = $event
                    "
                  />
                  <FormControl
                    :model-value="form.scoping.payment_terms || ''"
                    type="select"
                    :label="__('Payment terms')"
                    :options="paymentOptions"
                    :disabled="!editable"
                    @update:model-value="form.scoping.payment_terms = $event"
                  />
                  <FormControl
                    :model-value="form.scoping.amc_plan || ''"
                    type="select"
                    :label="__('AMC plan to recommend')"
                    :options="amcOptions"
                    :disabled="!editable"
                    @update:model-value="form.scoping.amc_plan = $event || null"
                  />
                </div>
                <div v-if="editable" class="flex flex-wrap items-center gap-3">
                  <Button
                    :label="__('Regenerate proposal')"
                    :disabled="dirty"
                    :tooltip="dirty ? __('Save your changes first') : ''"
                    :loading="regenerateAll.loading"
                    @click="regenerateProposal(false)"
                  >
                    <template #prefix>
                      <LucideRefreshCw class="size-4" aria-hidden="true" />
                    </template>
                  </Button>
                  <span class="text-p-sm text-ink-gray-6">{{
                    __(
                      "Rebuilds every section from the scoping and the libraries (and the narrative with AI). Sections you edited are kept."
                    )
                  }}</span>
                </div>
              </div>
            </details>

            <ProposalModules
              v-model:modules="form.modules"
              :catalogue="options?.catalogue || []"
              :solution-type="proposal.solution_type"
              :editable="editable"
            >
              <template #actions>
                <Button
                  v-if="editable"
                  class="ml-auto"
                  :label="__('Price from modules')"
                  :disabled="dirty || !form.modules.length"
                  :tooltip="dirty ? __('Save your changes first') : ''"
                  :loading="priceModules.loading"
                  @click="priceModules.submit({ name: proposalId })"
                />
              </template>
            </ProposalModules>

            <ProposalBlocks
              v-model:sections="form.sections"
              :proposal="proposalId"
              :editable="editable"
              :guidance="guidance"
              :section-types="options?.section_types || []"
              :busy="regenerating"
              @regenerate="regenerateSection($event, false)"
            >
              <template #pricing>
                <ProposalPricingSummary
                  :proposal="proposal"
                  :editable="editable"
                  @price="showPricing = true"
                  @changed="takePricing"
                />
              </template>
            </ProposalBlocks>

            <section
              v-if="proposal.revisions.length > 1"
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-label="__('Versions')"
            >
              <h2
                class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
              >
                {{ __("Versions") }}
              </h2>
              <ul role="list">
                <li
                  v-for="r in proposal.revisions"
                  :key="r.name"
                  class="border-b border-outline-gray-1 last:border-b-0"
                >
                  <router-link
                    :to="{
                      name: 'LeadProposal',
                      params: { leadId, proposalId: r.name },
                    }"
                    :aria-current="r.name === proposalId ? 'page' : undefined"
                    class="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-highlight"
                    :class="r.name === proposalId ? 'bg-brand-soft' : ''"
                  >
                    <span class="text-base text-ink-gray-8 tabular-nums">{{
                      __("Version {0}", String(r.revision_no + 1))
                    }}</span>
                    <span class="font-mono text-xs text-ink-gray-5">{{
                      r.name
                    }}</span>
                    <TaskyBadge
                      class="ml-auto"
                      :label="__(r.status)"
                      :tone="proposalTone(r.status)"
                    />
                  </router-link>
                </li>
              </ul>
            </section>
          </div>

          <div class="min-w-0">
            <div class="xl:sticky xl:top-0">
              <h2 class="mb-2 text-sm font-medium text-ink-gray-6">
                {{ __("What the client sees") }}
              </h2>
              <ProposalPreview
                :title="form.title"
                :client="proposal.client"
                :solution-type="proposal.solution_type"
                :valid-till="form.valid_till"
                :sections="form.sections"
                :quotation="proposal.quotation"
                :pricing-mode="form.pricing_mode"
                :modules="form.modules"
                :letter-head="letterHeadPreview"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <ProposalPricingDialog
      v-if="proposal"
      v-model:open="showPricing"
      :proposal="proposalId"
      @saved="onPriced"
    />

    <Dialog v-model:open="showSend" :title="__('Send the proposal')" size="lg">
      <form
        :id="sendFormId"
        class="flex flex-col gap-4"
        novalidate
        @submit.prevent="send"
      >
        <FormControl
          v-model="sendForm.recipients"
          type="email"
          :label="__('To')"
          :description="
            __('The client gets an email with the link, from the ERP site.')
          "
          required
        />
        <FormControl
          v-model="sendForm.message"
          type="textarea"
          :rows="5"
          :label="__('Message')"
          :placeholder="
            __('A short note above the link. Blank: a standard greeting.')
          "
        />
        <FormControl
          v-model="sendForm.attach_pdf"
          type="checkbox"
          :label="__('Attach the PDF too')"
        />
        <p v-if="sendError" role="alert" class="text-p-sm text-danger">
          {{ sendError }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="sendFormId"
            :label="__('Send proposal')"
            :loading="sendResource.loading"
            :disabled="!sendForm.recipients.trim()"
          />
        </div>
      </template>
    </Dialog>

    <!-- one confirm for the actions that can't be undone or write over edits -->
    <Dialog v-model:open="confirm.open" :title="confirm.title" size="md">
      <p class="text-p-base text-ink-gray-7">{{ confirm.message }}</p>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            :label="confirm.action"
            @click="runConfirmed"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useScreenSize } from "@/composables/screen";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  Dialog,
  Dropdown,
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSend from "~icons/lucide/send";
import LucideShare2 from "~icons/lucide/share-2";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import ClientProfileForm from "./ClientProfileForm.vue";
import ProposalAssistant from "./ProposalAssistant.vue";
import ProposalBlocks from "./ProposalBlocks.vue";
import ProposalModules from "./ProposalModules.vue";
import ProposalPreview from "./ProposalPreview.vue";
import ProposalPricingDialog from "./ProposalPricingDialog.vue";
import ProposalPricingSummary from "./ProposalPricingSummary.vue";
import ProposalScopingForm from "./ProposalScopingForm.vue";
import ProposalTracking from "./ProposalTracking.vue";
import {
  emptyProfile,
  emptyScoping,
  estimatePages,
  loadProposalOptions,
  proposalOptions,
  proposalTone,
  type ClientProfile,
  type Proposal,
  type ProposalModule,
  type ProposalOptions,
  type ProposalSection,
  type Scoping,
} from "./proposals";

const props = defineProps<{ leadId: string; proposalId: string }>();
const router = useRouter();
const { isMobileView } = useScreenSize();
const priceLabelId = `proposal-price-${useId()}`;
const sendFormId = `proposal-send-${useId()}`;

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);
const pricingModeOptions = [
  { label: __("Itemised"), value: "Itemised" },
  { label: __("Consolidated"), value: "Consolidated" },
];

const proposal = ref<Proposal>();
const form = reactive({
  title: "",
  /** "": the default letter head */
  letter_head: "",
  pricing_mode: "Itemised" as Proposal["pricing_mode"],
  valid_till: "" as string | null,
  requirements: "",
  client_profile: emptyProfile() as ClientProfile,
  scoping: emptyScoping() as Scoping,
  modules: [] as ProposalModule[],
  sections: [] as ProposalSection[],
});
const saved = ref("");

function snapshot() {
  return JSON.stringify(form);
}

function setProposal(p: Proposal) {
  proposal.value = p;
  form.title = p.title;
  form.letter_head = p.letter_head || "";
  form.pricing_mode = p.pricing_mode || "Itemised";
  form.valid_till = p.valid_till || "";
  form.requirements = p.requirements || "";
  form.client_profile = { ...emptyProfile(), ...(p.client_profile || {}) };
  form.scoping = { ...emptyScoping(), ...(p.scoping || {}) };
  form.modules = (p.modules || []).map((m) => ({ ...m }));
  form.sections = p.sections.map((s) => ({ ...s }));
  saved.value = snapshot();
}

const detail = createResource({
  url: "helpdesk.api.proposals.get_proposal",
  makeParams: () => ({ name: props.proposalId }),
  auto: true,
  onSuccess: setProposal,
});
watch(
  () => props.proposalId,
  () => {
    proposal.value = undefined;
    detail.reload();
  }
);

const isDraft = computed(() => proposal.value?.status === "Draft");
const editable = computed(() => !!(isDraft.value && proposal.value?.can_write));
const dirty = computed(() => editable.value && snapshot() !== saved.value);
const canSendStatus = computed(
  () =>
    !!proposal.value?.is_latest &&
    ["Draft", "Sent", "Viewed"].includes(proposal.value.status)
);
const sendTooltip = computed(() => {
  if (dirty.value) return __("Save your changes first");
  return proposal.value?.send_blockers[0] || "";
});
const pages = computed(() => estimatePages(form.sections));

const template = computed(() =>
  options.value?.templates?.find((t) => t.name === proposal.value?.template)
);
/** Each section type's guidance from the proposal's template, as the placeholder. */
const guidance = computed(() =>
  Object.fromEntries(
    (template.value?.sections ?? []).map((s) => [
      s.section_type,
      s.guidance || "",
    ])
  )
);

const timelineOptions = computed(() =>
  (options.value?.timelines ?? []).map((t) => ({
    label: t.title,
    value: t.title,
  }))
);
const paymentOptions = computed(() =>
  (options.value?.payment_terms ?? []).map((t) => ({ label: t, value: t }))
);
const amcOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(options.value?.amc_plans ?? []).map((p) => ({ label: p, value: p })),
]);

// --- letter head ---

const letterHeadOptions = computed(() => {
  const heads = options.value?.letter_heads ?? [];
  if (!heads.length) return [];
  const fallback = options.value?.default_letter_head;
  return [
    {
      label: fallback ? __("Default ({0})", fallback) : __("Default"),
      value: "",
    },
    ...heads.map((h) => ({ label: h.name, value: h.name })),
  ];
});

/** The letter head as saved; a pick not saved yet shows once saved. */
const letterHeadPreview = computed(() =>
  form.letter_head === (proposal.value?.letter_head || "")
    ? proposal.value?.letter_head_preview
    : null
);

// --- sharing: copy link, PDF, print ---

/** The ERP site's guest PDF for this proposal (a draft's through its preview). */
const pdfUrl = computed(() => {
  if (!proposal.value) return "";
  const url = new URL(proposal.value.preview_url);
  const token = url.pathname.split("/").pop();
  return `${
    url.origin
  }/api/method/tbo_smart.api.proposal_page.download_pdf?token=${token}${
    isDraft.value ? "&preview=1" : ""
  }`;
});

const shareOptions = computed(() => [
  {
    label: __("Copy link"),
    icon: "link",
    onClick: copyLink,
  },
  {
    label: __("Download PDF"),
    icon: "download",
    onClick: () => window.open(pdfUrl.value, "_blank", "noopener"),
  },
  {
    label: __("Print"),
    icon: "printer",
    onClick: () =>
      window.open(
        `${proposal.value?.preview_url}&print=1`,
        "_blank",
        "noopener"
      ),
  },
  {
    label: __("Preview link"),
    icon: "external-link",
    onClick: () =>
      window.open(proposal.value?.preview_url, "_blank", "noopener"),
  },
]);

async function writeClipboard(url: string) {
  try {
    await navigator.clipboard.writeText(url);
    toast.success(__("Link copied"));
  } catch {
    toast.info(url);
  }
}

/** A sent proposal's link is copied at once; a draft is shared (it goes out) after a confirm. */
function copyLink() {
  const p = proposal.value;
  if (!p) return;
  if (p.public_url) {
    writeClipboard(p.public_url);
    return;
  }
  if (dirty.value) {
    toast.warning(__("Save your changes first"));
    return;
  }
  if (p.share_blockers.length) {
    toast.warning(p.share_blockers[0]);
    return;
  }
  ask(
    __("Share this draft?"),
    __(
      "The proposal goes to the client as if sent, without an email: its quotation goes out, the lead moves to Proposal Sent, and the content is fixed. Changes after that need a revision."
    ),
    __("Share and copy link"),
    () => shareResource.submit({ name: props.proposalId })
  );
}

const shareResource = createResource({
  url: "helpdesk.api.proposals.share_proposal",
  method: "POST",
  onSuccess(d: { proposal: Proposal; url: string }) {
    setProposal(d.proposal);
    writeClipboard(d.url);
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't share it.")));
  },
});

// --- confirm ---

const confirm = reactive({
  open: false,
  title: "",
  message: "",
  action: "",
  run: null as null | (() => void),
});

function ask(title: string, message: string, action: string, run: () => void) {
  Object.assign(confirm, { open: true, title, message, action, run });
}

function runConfirmed() {
  confirm.open = false;
  confirm.run?.();
}

// --- save ---

const saveResource = createResource({
  url: "helpdesk.api.proposals.save_proposal",
  method: "POST",
  onSuccess(p: Proposal) {
    setProposal(p);
    toast.success(__("Proposal saved"));
  },
  onError(e: unknown) {
    toast.error(
      errorText(e, __("Couldn't save. Check your connection and try again."))
    );
  },
});

function save() {
  if (saveResource.loading || !dirty.value) return;
  saveResource.submit({
    name: props.proposalId,
    data: {
      title: form.title,
      letter_head: form.letter_head || null,
      pricing_mode: form.pricing_mode,
      valid_till: form.valid_till || null,
      requirements: form.requirements,
      client_profile: form.client_profile,
      scoping: form.scoping,
      modules: form.modules,
      sections: form.sections,
    },
  });
}

/** The server's new pricing and blockers, keeping unsaved edits to the text. */
function takePricing(p: Proposal) {
  const edits = dirty.value ? JSON.parse(snapshot()) : null;
  setProposal(p);
  if (edits) Object.assign(form, edits);
}

function onPriced(p: Proposal) {
  takePricing(p);
  toast.success(__("Pricing saved"));
}

const priceModules = createResource({
  url: "helpdesk.api.proposals.price_from_modules",
  method: "POST",
  onSuccess(p: Proposal) {
    takePricing(p);
    toast.success(__("Priced from the modules"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't price it from the modules.")));
  },
});

// --- regenerate ---

const regenerating = ref<number | null>(null);

function showWarnings(warnings?: string[]) {
  for (const warning of warnings ?? []) toast.warning(warning);
}

const regenerateOne = createResource({
  url: "helpdesk.api.proposals.regenerate_section",
  method: "POST",
  onSuccess(d: {
    proposal: Proposal;
    warnings: string[];
    confirm: string | null;
  }) {
    const index = regenerating.value;
    regenerating.value = null;
    if (d.confirm && index !== null) {
      ask(__("Write over your edits?"), d.confirm, __("Write over"), () =>
        regenerateSection(index, true)
      );
      return;
    }
    setProposal(d.proposal);
    showWarnings(d.warnings);
  },
  onError(e: unknown) {
    regenerating.value = null;
    toast.error(errorText(e, __("Couldn't regenerate it.")));
  },
});

function regenerateSection(index: number, force: boolean) {
  if (dirty.value) {
    toast.warning(__("Save your changes first"));
    return;
  }
  regenerating.value = index;
  regenerateOne.submit({ name: props.proposalId, index, force: force ? 1 : 0 });
}

const regenerateAll = createResource({
  url: "helpdesk.api.proposals.regenerate_proposal",
  method: "POST",
  onSuccess(d: { proposal: Proposal; warnings: string[]; kept: string[] }) {
    setProposal(d.proposal);
    showWarnings(d.warnings);
    if (d.kept?.length)
      ask(
        __("Some sections were kept"),
        __(
          "You edited these, so they weren't rebuilt: {0}.",
          d.kept.join(", ")
        ),
        __("Rebuild them too"),
        () => regenerateProposal(true)
      );
    else toast.success(__("Proposal regenerated"));
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't regenerate the proposal.")));
  },
});

function regenerateProposal(force: boolean) {
  regenerateAll.submit({ name: props.proposalId, force: force ? 1 : 0 });
}

// --- revision ---

const revisionResource = createResource({
  url: "helpdesk.api.proposals.create_revision",
  method: "POST",
  onSuccess(p: Proposal) {
    toast.success(__("Version {0} created", String(p.revision_no + 1)));
    router.push({
      name: "LeadProposal",
      params: { leadId: props.leadId, proposalId: p.name },
    });
  },
  onError(e: unknown) {
    toast.error(errorText(e, __("Couldn't create the revision.")));
  },
});

// --- send ---

const showPricing = ref(false);
const showSend = ref(false);
const sendError = ref("");
const sendForm = reactive({ recipients: "", message: "", attach_pdf: false });

function openSend() {
  sendForm.recipients =
    proposal.value?.tracking.sent_to || proposal.value?.lead_email || "";
  sendForm.message = "";
  sendForm.attach_pdf = false;
  sendError.value = "";
  showSend.value = true;
}

const sendResource = createResource({
  url: "helpdesk.api.proposals.send_proposal",
  method: "POST",
  onSuccess(p: Proposal) {
    setProposal(p);
    showSend.value = false;
    toast.success(__("Sent to {0}", p.tracking.sent_to || ""));
  },
  onError(e: unknown) {
    sendError.value = errorText(
      e,
      __("Couldn't send it. Check your connection and try again.")
    );
  },
});

function send() {
  if (sendResource.loading) return;
  sendError.value = "";
  sendResource.submit({
    name: props.proposalId,
    recipients: sendForm.recipients,
    message: sendForm.message,
    attach_pdf: sendForm.attach_pdf ? 1 : 0,
  });
}
</script>

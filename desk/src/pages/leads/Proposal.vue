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
        <Button
          :label="__('Preview link')"
          :link="proposal.preview_url"
          :title="
            __('Opens the client\'s page in a new tab; no view is counted')
          "
        >
          <!-- a phone shows the icon only; the label stays its accessible name -->
          <template #[previewSlot]>
            <LucideExternalLink class="size-4" aria-hidden="true" />
          </template>
        </Button>
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
                  <span :id="themeLabelId" class="text-xs text-ink-gray-5">{{
                    __("Theme")
                  }}</span>
                  <TabButtons
                    :model-value="form.theme"
                    :aria-labelledby="themeLabelId"
                    :options="themeOptions"
                    @update:model-value="editable && (form.theme = $event)"
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
            </section>

            <ProposalBlocks
              v-model:sections="form.sections"
              :proposal="proposalId"
              :editable="editable"
              :guidance="guidance"
              :section-types="options?.section_types || []"
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
                :theme="form.theme"
                :valid-till="form.valid_till"
                :sections="form.sections"
                :quotation="proposal.quotation"
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
  FormControl,
  TabButtons,
  toast,
} from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideSend from "~icons/lucide/send";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import ProposalBlocks from "./ProposalBlocks.vue";
import ProposalPreview from "./ProposalPreview.vue";
import ProposalPricingDialog from "./ProposalPricingDialog.vue";
import ProposalPricingSummary from "./ProposalPricingSummary.vue";
import ProposalTracking from "./ProposalTracking.vue";
import {
  loadProposalOptions,
  proposalOptions,
  proposalTone,
  type Proposal,
  type ProposalOptions,
  type ProposalSection,
} from "./proposals";

const props = defineProps<{ leadId: string; proposalId: string }>();
const router = useRouter();
const { isMobileView } = useScreenSize();
const previewSlot = computed(() => (isMobileView.value ? "icon" : "prefix"));
const themeLabelId = `proposal-theme-${useId()}`;
const sendFormId = `proposal-send-${useId()}`;

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);
const themeOptions = computed(() =>
  (options.value?.themes ?? ["TBO Teal", "Graphite"]).map((t) => ({
    label: __(t),
    value: t,
  }))
);

const proposal = ref<Proposal>();
const form = reactive({
  title: "",
  theme: "TBO Teal",
  /** "": the default letter head */
  letter_head: "",
  valid_till: "" as string | null,
  sections: [] as ProposalSection[],
});
const saved = ref("");

function snapshot() {
  return JSON.stringify(form);
}

function setProposal(p: Proposal) {
  proposal.value = p;
  form.title = p.title;
  form.theme = p.theme || "TBO Teal";
  form.letter_head = p.letter_head || "";
  form.valid_till = p.valid_till || "";
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

/** Each block type's guidance from the proposal's template, as the placeholder. */
const guidance = computed(() => {
  const template = options.value?.templates?.find(
    (t) => t.name === proposal.value?.template
  );
  return Object.fromEntries(
    (template?.sections ?? []).map((s) => [s.section_type, s.guidance || ""])
  );
});

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
      theme: form.theme,
      letter_head: form.letter_head || null,
      valid_till: form.valid_till || null,
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

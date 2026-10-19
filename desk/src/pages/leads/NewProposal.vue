<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <nav
          class="flex min-w-0 items-center gap-1.5 text-lg-medium"
          :aria-label="__('Breadcrumb')"
        >
          <router-link
            :to="{ name: 'Lead', params: { leadId } }"
            class="min-w-0 shrink truncate rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >{{ state.profile.name || leadId }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1 class="truncate text-ink-gray-9">{{ __("New proposal") }}</h1>
        </nav>
      </template>
      <template #right-header>
        <Button
          v-if="!chatOpen && options?.enabled"
          :label="__('Back to the assistant')"
          @click="chatOpen = true"
        />
        <!-- Generate stays a normal button; while something required is empty this says what,
             and the button (or the hint) takes presales to the first missing field -->
        <button
          v-if="missing.length && options?.enabled"
          type="button"
          class="hidden max-w-xs truncate rounded text-p-sm text-ink-gray-7 underline decoration-outline-gray-4 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight sm:inline"
          @click="focusMissing"
        >
          {{
            __("To generate, fill: {0}", missing.map((m) => m.label).join(", "))
          }}
        </button>
        <Button
          variant="solid"
          :label="__('Generate proposal')"
          :loading="create.loading"
          :disabled="!options?.enabled"
          @click="generate"
        >
          <!-- a phone shows the icon only; the label stays its accessible name -->
          <template #[iconSlot]>
            <LucideFileText class="size-4" aria-hidden="true" />
          </template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="options && !options.enabled"
          :icon="LucideCircleAlert"
          :title="__('Proposals are off on the ERP site')"
          :message="__('Switch on Proposals in TBO Smart Settings there.')"
        />
        <div
          v-else-if="options"
          class="grid grid-cols-1 gap-4"
          :class="chatOpen ? 'lg:grid-cols-2' : ''"
        >
          <div
            v-if="chatOpen"
            class="flex min-w-0 flex-col lg:sticky lg:top-0 lg:h-[calc(100vh-8rem)]"
          >
            <ProposalChat
              :state="state"
              :log="chatLog"
              class="h-full"
              :lead="leadId"
              :options="options"
              :missing="missing.map((m) => m.label)"
              :generating="create.loading"
              @skip="chatOpen = false"
              @generate="generate"
            />
          </div>

          <!-- the live summary: the scoping form, filled as the chat goes; edit anything -->
          <div class="flex min-w-0 flex-col gap-4" :aria-label="__('Summary')">
            <p v-if="error" role="alert" class="text-p-sm text-danger">
              {{ error }}
            </p>
            <section
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="profileId"
            >
              <h2 :id="profileId" class="text-base-medium text-ink-gray-9">
                {{ __("Client profile") }}
                <span
                  v-if="!profileFilled"
                  class="ml-1 text-p-sm font-normal text-ink-gray-5"
                  >{{ __("(industry and pain points required)") }}</span
                >
              </h2>
              <ClientProfileForm
                v-model="state.profile"
                :lead="leadId"
                :can-read="!!options.ai"
              />
            </section>

            <section
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="reqId"
            >
              <h2 :id="reqId" class="text-base-medium text-ink-gray-9">
                {{ __("Customer requirements") }}
              </h2>
              <FormControl
                v-model="state.requirements"
                type="textarea"
                :rows="4"
                :aria-labelledby="reqId"
                maxlength="8000"
              />
            </section>

            <section
              class="flex flex-col gap-4 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="formId"
            >
              <h2 :id="formId" class="text-base-medium text-ink-gray-9">
                {{ __("What the proposal covers") }}
              </h2>
              <FormControl
                :model-value="state.template"
                type="select"
                :label="__('Template')"
                :options="templateOptions"
                :description="chosen?.description || ''"
                @update:model-value="pickTemplate"
              />
              <ProposalScopingForm
                v-model="state.scoping"
                :questions="chosen?.questions"
                :catalogue="options.catalogue || []"
                :solution-type="chosen?.solution_type"
                :hosting="options.hosting || []"
              />
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <FormControl
                  :model-value="
                    state.scoping.timeline_template || suggested || ''
                  "
                  type="select"
                  :label="__('Timeline')"
                  :options="timelineOptions"
                  @update:model-value="
                    setScoping({ timeline_template: $event || null })
                  "
                />
                <FormControl
                  :model-value="
                    state.scoping.payment_terms ||
                    options.payment_terms?.[0] ||
                    ''
                  "
                  type="select"
                  :label="__('Payment terms')"
                  :options="
                    (options.payment_terms || []).map((t) => ({
                      label: t,
                      value: t,
                    }))
                  "
                  @update:model-value="
                    setScoping({ payment_terms: $event || null })
                  "
                />
                <FormControl
                  :model-value="state.scoping.amc_plan || ''"
                  type="select"
                  :label="__('AMC plan to recommend')"
                  :options="amcOptions"
                  @update:model-value="
                    setScoping({ amc_plan: $event || null, amc: !!$event })
                  "
                />
              </div>
              <FormControl
                v-if="options.ai"
                v-model="aiDraft"
                type="checkbox"
                :label="
                  __(
                    'Write the summary, background, challenges, benefits and customisations with AI (one call)'
                  )
                "
              />
              <p class="text-p-sm text-ink-gray-6">
                {{
                  __(
                    "Everything else (overview, scope, modules, timeline, investment, terms) comes from the template and the libraries, at no AI cost. You can edit every section after."
                  )
                }}
              </p>
            </section>
          </div>
        </div>
        <div
          v-else
          class="h-64 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          aria-busy="true"
          :aria-label="__('Loading')"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import { useScreenSize } from "@/composables/screen";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileText from "~icons/lucide/file-text";
import ClientProfileForm from "./ClientProfileForm.vue";
import ProposalChat, {
  type ChatLine,
  type ChatState,
} from "./ProposalChat.vue";
import ProposalScopingForm from "./ProposalScopingForm.vue";
import {
  emptyProfile,
  emptyScoping,
  loadProposalOptions,
  proposalOptions,
  suggestTimeline,
  type ClientProfile,
  type Proposal,
  type ProposalOptions,
  type Scoping,
} from "./proposals";

const props = defineProps<{ leadId: string }>();
const MAIN_TEMPLATE = "ERPNext Implementation";
const { isMobileView } = useScreenSize();
const iconSlot = computed(() => (isMobileView.value ? "icon" : "prefix"));
const router = useRouter();
const reqId = `new-proposal-req-${useId()}`;
const formId = `new-proposal-form-${useId()}`;
const profileId = `new-proposal-profile-${useId()}`;

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);

/** One state for the chat and the summary: whichever presales uses, the other follows. */
const state = reactive<ChatState>({
  template: "",
  profile: emptyProfile(),
  requirements: "",
  scoping: emptyScoping(),
});
const chatLog = reactive<ChatLine[]>([]);
const chatOpen = ref(true);
const aiDraft = ref(true);
const error = ref("");

function setScoping(patch: Partial<Scoping>) {
  Object.assign(state.scoping, patch);
}

const templates = computed(() =>
  (options.value?.templates ?? []).filter((t) => t.enabled)
);
const chosen = computed(() =>
  templates.value.find((t) => t.name === state.template)
);
const templateOptions = computed(() => [
  ...templates.value.map((t) => ({ label: t.template_name, value: t.name })),
  { label: __("Blank (every section, no template)"), value: "" },
]);

const PROFILE_LABELS: Record<string, string> = {
  industry: __("Industry"),
  pain_points: __("Pain points"),
};
/** The client profile fields still empty that a proposal needs, in the form's order. */
const missing = computed(() =>
  (options.value?.profile_required ?? ["industry", "pain_points"])
    .filter(
      (field) => !(state.profile[field as keyof ClientProfile] || "").trim()
    )
    .map((field) => ({ field, label: PROFILE_LABELS[field] || field }))
);
const profileFilled = computed(() => !missing.value.length);

/** To the first missing field in the summary, ready to type. */
function focusMissing() {
  const first = missing.value[0];
  if (!first) return;
  // the attribute lands on the field's wrapper or on the input itself
  const marked = document.querySelector<HTMLElement>(
    `[data-profile-field="${first.field}"]`
  );
  const box = marked?.matches("input, textarea")
    ? marked
    : marked?.querySelector<HTMLElement>("input, textarea");
  box?.scrollIntoView({ behavior: "smooth", block: "center" });
  box?.focus({ preventScroll: true });
}
const ready = computed(
  () => !!options.value?.enabled && profileFilled.value && !create.loading
);

const suggested = computed(() =>
  suggestTimeline(
    options.value?.timelines ?? [],
    state.scoping,
    options.value?.catalogue ?? []
  )
);
const timelineOptions = computed(() =>
  (options.value?.timelines ?? []).map((t) => ({
    label:
      t.title === suggested.value ? __("{0} (suggested)", t.title) : t.title,
    value: t.title,
  }))
);
const amcOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(options.value?.amc_plans ?? []).map((p) => ({ label: p, value: p })),
]);

/** A template brings its default modules, unless the person already picked their own. */
function pickTemplate(name: string) {
  const before = chosen.value?.default_modules ?? [];
  const untouched =
    !state.scoping.modules.length ||
    JSON.stringify(state.scoping.modules) === JSON.stringify(before);
  const next = templates.value.find((t) => t.name === name);
  state.template = name;
  if (untouched) state.scoping.modules = [...(next?.default_modules ?? [])];
}

watch(
  templates,
  (list) => {
    // TBO's main line first; the requirements read can pick another
    if (list.length && !state.template)
      pickTemplate(
        (list.find((t) => t.name === MAIN_TEMPLATE) || list[0]).name
      );
  },
  { immediate: true }
);
watch(
  () => options.value?.ai,
  (on) => (aiDraft.value = !!on),
  { immediate: true }
);

createResource({
  url: "helpdesk.api.proposals.get_client_profile",
  makeParams: () => ({ lead: props.leadId }),
  auto: true,
  onSuccess(d: { profile?: Partial<ClientProfile> }) {
    state.profile = {
      ...emptyProfile(),
      ...(d.profile || {}),
      ...nonEmpty(state.profile),
    };
  },
});

function nonEmpty(profile: ClientProfile): Partial<ClientProfile> {
  return Object.fromEntries(Object.entries(profile).filter(([, v]) => v));
}

const create = createResource({
  url: "helpdesk.api.proposals.create_proposal",
  method: "POST",
  onSuccess(data: { proposal: Proposal; warnings: string[] }) {
    for (const warning of data.warnings ?? []) toast.warning(warning);
    router.replace({
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

function generate() {
  if (!profileFilled.value) {
    error.value = __(
      "To generate, fill: {0}",
      missing.value.map((m) => m.label).join(", ")
    );
    focusMissing();
    return;
  }
  if (!ready.value) return;
  error.value = "";
  const s = state;
  create.submit({
    lead: props.leadId,
    template: s.template || null,
    ai_draft: options.value?.ai && aiDraft.value ? 1 : 0,
    scoping: {
      ...s.scoping,
      integrations: s.scoping.integrations.trim(),
      timeline_template: s.scoping.timeline_template || suggested.value,
      customisations: s.scoping.customisations.filter((c) => c.item.trim()),
    },
    requirements: s.requirements,
    client_profile: s.profile,
    chat: chatLog,
  });
}
</script>

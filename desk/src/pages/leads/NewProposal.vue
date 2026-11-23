<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <Button
          class="mr-2 shrink-0"
          variant="ghost"
          :label="__('Back')"
          :tooltip="__('Back')"
          @click="goBack"
        >
          <template #icon>
            <LucideArrowLeft class="size-4" aria-hidden="true" />
          </template>
        </Button>
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
          <h1 class="truncate text-ink-gray-9">
            {{ proposalId ? __("Edit proposal") : __("New proposal") }}
          </h1>
        </nav>
      </template>
      <template #right-header>
        <Button
          v-if="!chatOpen && options?.enabled"
          size="md"
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
          size="md"
          :label="proposalId ? __('Update proposal') : __('Generate proposal')"
          :loading="busy"
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

    <div class="relative flex-1 overflow-auto">
      <div class="flex w-full flex-col gap-4 px-4 pb-8 pt-4 md:px-8">
        <TaskyState
          v-if="options && !options.enabled"
          class="rounded-xl border border-outline-gray-2 bg-surface-base py-14"
          :icon="LucideCircleAlert"
          :title="__('Proposals are off on the ERP site')"
          :message="__('Switch on Proposals in TBO Smart Settings there.')"
        />
        <div
          v-else-if="options && (!proposalId || existing.data)"
          class="grid grid-cols-1 gap-5"
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
              :generating="busy"
              :ready="profileLoaded"
              @skip="chatOpen = false"
              @generate="generate"
            />
          </div>

          <!-- the live summary: the scoping form, filled as the chat goes; edit anything -->
          <div class="flex min-w-0 flex-col gap-5" :aria-label="__('Summary')">
            <p v-if="error" role="alert" class="text-p-sm text-danger">
              {{ error }}
            </p>
            <section
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="profileId"
            >
              <h2
                :id="profileId"
                class="text-base font-semibold text-ink-gray-9"
              >
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
              <h2 :id="reqId" class="text-base font-semibold text-ink-gray-9">
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
              <h2 :id="formId" class="text-base font-semibold text-ink-gray-9">
                {{ __("What the proposal covers") }}
              </h2>
              <ProposalImplementation
                :template="state.template"
                :scoping="state.scoping"
                :templates="templates"
                @change="choose"
              />
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
                :hidden="pickerAsks"
                :branch-rate="options.branch_rate"
              />
              <div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <ProposalTimelineField
                  :template="state.scoping.timeline_template"
                  :days="state.scoping.timeline_days || 0"
                  :timelines="options.timelines || []"
                  :suggested="suggested"
                  @update="setScoping"
                />
                <ProposalPaymentTermsField
                  :terms="state.scoping.payment_terms"
                  :milestones="state.scoping.payment_milestones || []"
                  :templates="options.payment_terms || []"
                  @update="setScoping"
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
                v-if="options.ai && !proposalId"
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

            <section
              v-if="
                state.scoping.modules.length ||
                state.scoping.customisations.length ||
                state.scoping.branches
              "
              class="flex flex-col gap-3 rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-labelledby="priceId"
            >
              <h2 :id="priceId" class="text-base font-semibold text-ink-gray-9">
                {{ __("Price") }}
              </h2>
              <ProposalPriceEstimate
                v-model:scoping="state.scoping"
                v-model:prices="prices"
                :scoping="state.scoping"
                :catalogue="options.catalogue || []"
                :main-label="mainLabel"
                :currency="options.currency || 'INR'"
                :branch-rate="options.branch_rate"
              />
            </section>
          </div>
        </div>
        <div
          v-else
          class="h-64 animate-pulse rounded-xl bg-surface-gray-3"
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
import { Button, call, createResource, FormControl, toast } from "frappe-ui";
import { computed, reactive, ref, useId, watch } from "vue";
import { useRouter } from "vue-router";
import LucideArrowLeft from "~icons/lucide/arrow-left";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileText from "~icons/lucide/file-text";
import ClientProfileForm from "./ClientProfileForm.vue";
import ProposalChat, {
  type ChatLine,
  type ChatState,
} from "./ProposalChat.vue";
import ProposalImplementation from "./ProposalImplementation.vue";
import ProposalPaymentTermsField from "./ProposalPaymentTermsField.vue";
import ProposalPriceEstimate from "./ProposalPriceEstimate.vue";
import ProposalScopingForm from "./ProposalScopingForm.vue";
import ProposalTimelineField from "./ProposalTimelineField.vue";
import {
  emptyProfile,
  emptyScoping,
  erpAddons,
  implementationOf,
  loadProposalOptions,
  mainAppLabel,
  warnDropped,
  proposalOptions,
  suggestTimeline,
  type ClientProfile,
  type ImplementationChoice,
  type ProposalModule,
  type Proposal,
  type Question,
  type ProposalOptions,
  type Scoping,
} from "./proposals";

const props = defineProps<{
  leadId: string;
  /** a draft proposal to edit here; none makes a new one */
  proposalId?: string;
}>();
const MAIN_TEMPLATE = "ERPNext Implementation";
const { isMobileView } = useScreenSize();
const iconSlot = computed(() => (isMobileView.value ? "icon" : "prefix"));
const router = useRouter();
const reqId = `new-proposal-req-${useId()}`;
const formId = `new-proposal-form-${useId()}`;
const profileId = `new-proposal-profile-${useId()}`;
const priceId = `new-proposal-price-${useId()}`;

loadProposalOptions();
const options = computed(
  () => proposalOptions.data as ProposalOptions | undefined
);

/** To where they came from; straight to the lead when the page was opened from a link. */
function goBack() {
  if (window.history.state?.back) router.back();
  else router.push({ name: "Lead", params: { leadId: props.leadId } });
}

/** One state for the chat and the summary: whichever presales uses, the other follows. */
const state = reactive<ChatState>({
  template: "",
  profile: emptyProfile(),
  requirements: "",
  scoping: emptyScoping(),
});
const chatLog = reactive<ChatLine[]>([]);
/**
 * By Module, the prices typed on the Price card, set on the proposal's modules by hand (by App
 * or Custom the prices are in the scoping)
 */
const prices = ref<Record<string, number>>({});
// a module taken off loses its typed price, so adding it back starts from the list price
watch(
  () => state.scoping.modules,
  (modules) => {
    const kept = Object.entries(prices.value).filter(([m]) =>
      modules.includes(m)
    );
    if (kept.length !== Object.keys(prices.value).length)
      prices.value = Object.fromEntries(kept);
  },
  { deep: true }
);
const keeping = ref(false);
const busy = computed(() => create.loading || keeping.value);
// editing, the assistant stays shut so it doesn't ask again what the proposal already has
const chatOpen = ref(!props.proposalId);
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
// a proposal changes template, it can't go blank
const templateOptions = computed(() => [
  ...templates.value.map((t) => ({ label: t.template_name, value: t.name })),
  ...(props.proposalId
    ? []
    : [{ label: __("Blank (every section, no template)"), value: "" }]),
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
  () => !!options.value?.enabled && profileFilled.value && !busy.value
);

const suggested = computed(() =>
  suggestTimeline(
    options.value?.timelines ?? [],
    state.scoping,
    options.value?.catalogue ?? []
  )
);
const amcOptions = computed(() => [
  { label: __("None"), value: "" },
  ...(options.value?.amc_plans ?? []).map((p) => ({ label: p, value: p })),
]);

const kind = computed(() => implementationOf(chosen.value?.solution_type));
const mainLabel = computed(() => mainAppLabel(chosen.value?.solution_type));
/** On ERP the picker owns the mobile app, and customisations show once picked there. */
const pickerAsks = computed<Question[]>(() =>
  kind.value !== "ERP"
    ? []
    : erpAddons(state.scoping).includes("customisation")
    ? ["mobile_app"]
    : ["mobile_app", "customisation"]
);

function choose(next: ImplementationChoice) {
  state.template = next.template;
  state.scoping = next.scoping;
}

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
    if (list.length && !state.template && !props.proposalId)
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

/** The chat starts once the lead's profile is in, so it skips what is already known. */
const profileLoaded = ref(false);
createResource({
  url: "helpdesk.api.proposals.get_client_profile",
  makeParams: () => ({ lead: props.leadId }),
  // editing, the proposal's own profile is the one
  auto: !props.proposalId,
  onSuccess(d: { profile?: Partial<ClientProfile> }) {
    state.profile = {
      ...emptyProfile(),
      ...(d.profile || {}),
      ...nonEmpty(state.profile),
    };
    profileLoaded.value = true;
  },
  onError() {
    profileLoaded.value = true;
  },
});

function nonEmpty(profile: ClientProfile): Partial<ClientProfile> {
  return Object.fromEntries(Object.entries(profile).filter(([, v]) => v));
}

/** The proposal being edited, its scoping, profile and prices in the form. */
const existing = createResource({
  url: "helpdesk.api.proposals.get_proposal",
  makeParams: () => ({ name: props.proposalId }),
  auto: !!props.proposalId,
  onSuccess(p: Proposal) {
    state.template = p.template || "";
    state.profile = { ...emptyProfile(), ...(p.client_profile || {}) };
    state.requirements = p.requirements || "";
    // its modules as they are now, which the builder may have changed since
    state.scoping = {
      ...emptyScoping(),
      ...(p.scoping || {}),
      modules: p.modules.map((m) => m.module_name),
    };
    chatLog.splice(
      0,
      chatLog.length,
      ...(p.chat || []).map(({ role, text }) => ({ role, text }))
    );
    prices.value = Object.fromEntries(
      p.modules
        .filter((m) => m.rate_overridden)
        .map((m) => [m.module_name, m.rate])
    );
    profileLoaded.value = true;
  },
  onError(e: unknown) {
    error.value = errorText(e, __("Couldn't load the proposal."));
  },
});

const create = createResource({
  url: "helpdesk.api.proposals.create_proposal",
  method: "POST",
  async onSuccess(data: { proposal: Proposal; warnings: string[] }) {
    for (const warning of data.warnings ?? []) toast.warning(warning);
    warnDropped(scopingToSend(), data.proposal.scoping);
    await keepPrices(data.proposal);
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

/**
 * By Module, the proposal's modules at the Price card's prices: a priced one set by hand, the
 * others back on their list price. By App or Custom the modules' own prices don't price the
 * quotation, so they stay as they are.
 */
function pricedModules(modules: ProposalModule[]): ProposalModule[] {
  if (state.scoping.price_basis !== "Module") return modules;
  const typed = prices.value;
  return modules.map((m) =>
    m.module_name in typed
      ? { ...m, rate: typed[m.module_name], rate_overridden: 1 }
      : { ...m, rate_overridden: 0 }
  );
}

/** The Price card's prices, set by hand on the new proposal's modules. */
async function keepPrices(proposal: Proposal) {
  const modules = pricedModules(proposal.modules);
  if (!modules.some((m) => m.rate_overridden)) return;
  keeping.value = true;
  try {
    await call("helpdesk.api.proposals.save_proposal", {
      name: proposal.name,
      data: { modules },
    });
  } catch (e) {
    toast.warning(
      errorText(
        e,
        __(
          "The proposal is made, but the prices you typed weren't saved. Set them in its Modules."
        )
      )
    );
  } finally {
    keeping.value = false;
  }
}

/**
 * The edited proposal brought up to this page: a new template or other modules first (the ERP
 * site rebuilds its modules), then the profile, scoping and prices, then its sections rebuilt
 * (those edited by hand are kept). Back to the builder after.
 */
async function update() {
  const before = existing.data as Proposal;
  const name = before.name;
  const scoping = scopingToSend();
  keeping.value = true;
  try {
    let current = before;
    const warnings: string[] = [];
    const sameModules =
      JSON.stringify(scoping.modules) ===
      JSON.stringify(before.modules.map((m) => m.module_name));
    if (
      state.template &&
      (state.template !== before.template || !sameModules)
    ) {
      const d = await call("helpdesk.api.proposals.change_template", {
        name,
        template: state.template,
        scoping,
      });
      current = d.proposal;
      warnings.push(...(d.warnings ?? []));
    }
    const saved = await call("helpdesk.api.proposals.save_proposal", {
      name,
      data: {
        requirements: state.requirements,
        client_profile: state.profile,
        scoping,
        modules: pricedModules(current.modules),
      },
    });
    warnDropped(scoping, saved?.scoping);
    const r = await call("helpdesk.api.proposals.regenerate_proposal", {
      name,
      force: 0,
    });
    warnings.push(...(r.warnings ?? []));
    for (const warning of warnings) toast.warning(warning);
    if (r.kept?.length)
      toast.info(__("Kept your edits in: {0}", r.kept.join(", ")));
    else toast.success(__("Proposal updated"));
    backToBuilder();
  } catch (e) {
    error.value = errorText(
      e,
      __("Couldn't update the proposal. Check your connection and try again.")
    );
  } finally {
    keeping.value = false;
  }
}

/** To the builder it came from, else to it fresh, so Back there isn't this page again. */
function backToBuilder() {
  if (window.history.state?.back) router.back();
  else
    router.replace({
      name: "LeadProposal",
      params: { leadId: props.leadId, proposalId: props.proposalId },
    });
}

function scopingToSend(): Scoping {
  const s = state.scoping;
  return {
    ...s,
    integrations: s.integrations.trim(),
    timeline_template: s.timeline_template || suggested.value,
    customisations: s.customisations.filter((c) => c.item.trim()),
  };
}

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
  if (props.proposalId) return update();
  const s = state;
  create.submit({
    lead: props.leadId,
    template: s.template || null,
    ai_draft: options.value?.ai && aiDraft.value ? 1 : 0,
    scoping: scopingToSend(),
    requirements: s.requirements,
    client_profile: s.profile,
    chat: chatLog,
  });
}
</script>

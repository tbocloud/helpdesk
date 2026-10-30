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
            class="shrink-0 rounded text-ink-gray-6 hover:text-ink-gray-8 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >{{ __("Leads") }}</router-link
          >
          <LucideChevronRight
            class="size-4 shrink-0 text-ink-gray-4"
            aria-hidden="true"
          />
          <h1 class="truncate text-ink-gray-9">
            {{ lead?.lead_name || leadId }}
          </h1>
        </nav>
      </template>
      <template v-if="lead" #right-header>
        <!-- Call and Edit are icons on a phone, so Move stage keeps its room; `label` names them -->
        <Button
          v-if="canCall"
          :label="__('Call')"
          :loading="clickToCall.loading"
          :tooltip="__('MyOperator rings your phone, then the lead')"
          @click="clickToCall.submit({ name: leadId })"
        >
          <template #prefix>
            <LucidePhone class="size-4" aria-hidden="true" />
          </template>
          <span class="hidden sm:inline">{{ __("Call") }}</span>
        </Button>
        <!-- for a call made outside MyOperator; only once the ERP site can log it -->
        <Button
          v-if="options?.can_log_call"
          :label="__('Log call')"
          @click="showLogCall = true"
        >
          <template #prefix>
            <LucidePhoneForwarded class="size-4" aria-hidden="true" />
          </template>
          <span class="hidden lg:inline">{{ __("Log call") }}</span>
        </Button>
        <Button :label="__('Edit')" @click="showEdit = true">
          <template #prefix>
            <LucidePencil class="size-4" aria-hidden="true" />
          </template>
          <span class="hidden sm:inline">{{ __("Edit") }}</span>
        </Button>
        <Button
          variant="solid"
          :label="__('Move stage')"
          :disabled="!stageChoices.length"
          :tooltip="
            stageChoices.length
              ? ''
              : __('This lead can\'t move from its current stage.')
          "
          @click="openStageDialog"
        />
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-auto">
      <div class="mx-auto w-full max-w-6xl px-4 py-5 md:px-6">
        <TaskyState
          v-if="detail.error && !data"
          error
          :icon="LucideCircleAlert"
          :title="__('Couldn\'t load the lead')"
          :message="
            errorText(detail.error, __('Check your connection and try again.'))
          "
        >
          <Button :label="__('Try again')" @click="detail.reload()" />
          <Button :label="__('Back to leads')" :route="{ name: 'Leads' }" />
        </TaskyState>

        <div
          v-else-if="!data"
          class="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]"
          aria-busy="true"
          :aria-label="__('Loading')"
        >
          <div
            class="h-80 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          />
          <div
            class="h-80 animate-pulse rounded-xl border border-outline-gray-2 bg-surface-gray-1"
          />
        </div>

        <div v-else class="grid grid-cols-1 gap-4 lg:grid-cols-[20rem_1fr]">
          <LeadDocuments
            class="lg:col-span-2"
            :lead-id="leadId"
            :chain="data.documents"
            :can-write="!!lead?.can_write"
          />
          <div class="flex min-w-0 flex-col gap-4">
            <section
              class="rounded-xl border border-outline-gray-2 bg-surface-base"
              :aria-label="__('Details')"
            >
              <div
                class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
              >
                <h2 class="text-base-medium text-ink-gray-9">
                  {{ __("Details") }}
                </h2>
                <TaskyBadge
                  v-if="lead?.tbo_stage"
                  class="ml-auto"
                  :label="stageLabel(options, lead.tbo_stage)"
                  :tone="stageTone(options, lead.tbo_stage)"
                />
              </div>
              <dl class="flex flex-col gap-3 px-4 py-4">
                <div
                  v-for="field in detailFields"
                  :key="field.label"
                  class="flex flex-col gap-0.5"
                >
                  <dt class="text-xs text-ink-gray-5">{{ field.label }}</dt>
                  <dd
                    class="min-w-0 break-words text-base text-ink-gray-8"
                    :class="field.mono ? 'font-mono tabular-nums' : ''"
                  >
                    <a
                      v-if="field.href"
                      :href="field.href"
                      class="rounded underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
                      >{{ field.value }}</a
                    >
                    <template v-else>{{ field.value }}</template>
                  </dd>
                </div>
              </dl>
            </section>
            <template v-if="lead?.place">
              <LeadPlace
                :lead-id="leadId"
                :place="lead.place"
                :can-write="!!lead.can_write"
                @saved="detail.reload()"
              />
              <LeadPhotos :lead-id="leadId" :can-write="!!lead.can_write" />
            </template>
            <LeadAISuggests :lead-id="leadId" @changed="detail.reload()" />
            <LeadQuotations :quotations="data.quotations || []" />
            <LeadProposals
              :lead-id="leadId"
              :proposals="
                (data.proposals || []).filter(
                  (p) => (p.document_type || 'Proposal') === 'Proposal'
                )
              "
              :can-write="!!lead?.can_write"
            />
          </div>

          <section
            class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base"
            :aria-label="__('Timeline')"
          >
            <h2
              class="border-b border-outline-gray-1 px-4 py-3 text-base-medium text-ink-gray-9"
            >
              {{ __("Timeline") }}
            </h2>
            <form
              class="flex flex-col gap-2 border-b border-outline-gray-1 px-4 py-4"
              @submit.prevent="submitNote"
            >
              <FormControl
                v-model="note"
                type="textarea"
                :rows="3"
                :label="__('Add a note')"
                :placeholder="
                  __('What was said, what was agreed, what\'s next')
                "
              />
              <p v-if="noteError" role="alert" class="text-p-sm text-danger">
                {{ noteError }}
              </p>
              <div class="flex justify-end">
                <Button
                  type="submit"
                  :label="__('Add note')"
                  :loading="addNote.loading"
                  :disabled="!note.trim()"
                />
              </div>
            </form>
            <p
              v-if="!data.timeline?.length"
              class="px-4 py-6 text-p-sm text-ink-gray-6"
            >
              {{
                __(
                  "Nothing here yet. Notes and stage moves from here and the ERP site show up in this timeline."
                )
              }}
            </p>
            <ol v-else role="list" class="flex flex-col">
              <li
                v-for="(entry, i) in data.timeline"
                :key="entry.ref || i"
                class="flex gap-3 border-b border-outline-gray-1 px-4 py-3 last:border-b-0"
              >
                <component
                  :is="timelineIcon(entry)"
                  class="mt-0.5 size-4 shrink-0"
                  :class="
                    entry.call && entry.status === 'missed'
                      ? 'text-danger'
                      : 'text-ink-gray-5'
                  "
                  aria-hidden="true"
                />
                <div class="flex min-w-0 flex-1 flex-col gap-1">
                  <LeadCallEntry v-if="entry.call" :entry="entry" />
                  <p
                    v-else-if="entry.text"
                    class="whitespace-pre-line break-words"
                    :class="
                      entry.kind === 'note'
                        ? 'text-p-sm text-ink-gray-8'
                        : 'text-base-medium text-ink-gray-9'
                    "
                  >
                    <span class="sr-only"
                      >{{ TIMELINE_LABELS[entry.kind] }}: </span
                    >{{ entry.text }}
                  </p>
                  <p class="text-xs text-ink-gray-5">
                    {{ entry.who_name || entry.who }}
                    <template v-if="entry.at">
                      <span v-if="entry.who" aria-hidden="true"> · </span>
                      <time
                        :datetime="entry.at"
                        :title="dayjs(entry.at).format('D MMM YYYY, h:mm a')"
                        >{{ dayjs(entry.at).fromNow() }}</time
                      >
                    </template>
                  </p>
                </div>
              </li>
            </ol>
          </section>
        </div>
      </div>
    </div>

    <LogCallDialog
      v-model:open="showLogCall"
      :lead-id="leadId"
      @logged="detail.reload()"
    />
    <LeadFormDialog
      v-if="lead"
      v-model:open="showEdit"
      :lead="lead"
      @saved="detail.reload()"
    />

    <Dialog v-model:open="showStage" :title="__('Move stage')" size="md">
      <form
        :id="stageFormId"
        class="flex flex-col gap-4"
        @submit.prevent="submitStage"
      >
        <fieldset class="flex flex-col gap-2">
          <legend class="mb-1 text-p-sm text-ink-gray-6">
            {{
              __("Now {0}. Move it to:", stageLabel(options, lead?.tbo_stage))
            }}
          </legend>
          <label
            v-for="stage in stageChoices"
            :key="stage.name"
            class="flex min-h-[36px] cursor-pointer items-center gap-2 rounded-md px-2 hover:bg-surface-gray-1"
          >
            <input
              v-model="nextStage"
              type="radio"
              name="lead-stage"
              :value="stage.name"
              class="size-4 border-outline-gray-4 text-ink-gray-9 focus-visible:ring-2 focus-visible:ring-highlight"
            />
            <span class="text-base text-ink-gray-8">{{
              stage.label || stage.name
            }}</span>
          </label>
        </fieldset>
        <FormControl
          v-model="stageNote"
          type="textarea"
          :rows="3"
          :label="__('Note (optional)')"
          :placeholder="__('Why it moved, for whoever picks it up next')"
        />
        <p v-if="stageError" role="alert" class="text-p-sm text-danger">
          {{ stageError }}
        </p>
      </form>
      <template #actions="{ close }">
        <div class="flex justify-end gap-2">
          <Button :label="__('Cancel')" @click="close" />
          <Button
            variant="solid"
            type="submit"
            :form="stageFormId"
            :label="
              nextStage
                ? __('Move to {0}', stageLabel(options, nextStage))
                : __('Move stage')
            "
            :disabled="!nextStage"
            :loading="setStage.loading"
          />
        </div>
      </template>
    </Dialog>
  </div>
</template>

<script setup lang="ts">
import LayoutHeader from "@/components/LayoutHeader.vue";
import TaskyBadge from "@/components/TaskyBadge.vue";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  Dialog,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideBot from "~icons/lucide/bot";
import LucideCalendar from "~icons/lucide/calendar";
import LucideChevronRight from "~icons/lucide/chevron-right";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileText from "~icons/lucide/file-text";
import LucideHistory from "~icons/lucide/history";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneForwarded from "~icons/lucide/phone-forwarded";
import LucidePhoneIncoming from "~icons/lucide/phone-incoming";
import LucidePhoneMissed from "~icons/lucide/phone-missed";
import LucidePhoneOutgoing from "~icons/lucide/phone-outgoing";
import LucidePencil from "~icons/lucide/pencil";
import LeadAISuggests from "./LeadAISuggests.vue";
import LeadCallEntry from "./LeadCallEntry.vue";
import LucideScrollText from "~icons/lucide/scroll-text";
import LeadFormDialog from "./LeadFormDialog.vue";
import LeadPhotos from "./LeadPhotos.vue";
import LeadPlace from "./LeadPlace.vue";
import LeadDocuments from "./LeadDocuments.vue";
import LogCallDialog from "./LogCallDialog.vue";
import LeadProposals from "./LeadProposals.vue";
import LeadQuotations from "./LeadQuotations.vue";
import {
  loadLeadOptions,
  leadOptions,
  ownerName,
  stageLabel,
  stageTone,
  useClickToCall,
  type LeadDetail,
  type LeadOptions,
  type LeadStage,
  type LeadTimelineEntry,
} from "./leads";

const props = defineProps<{ leadId: string }>();

const TIMELINE_ICONS: Record<LeadTimelineEntry["kind"], Component> = {
  note: LucideMessageSquare,
  call: LucidePhone,
  activity: LucideHistory,
  meeting: LucideCalendar,
  stage: LucideArrowRight,
  quotation: LucideFileText,
  ai: LucideBot,
  proposal: LucideScrollText,
};
const TIMELINE_LABELS: Record<LeadTimelineEntry["kind"], string> = {
  note: __("Note"),
  call: __("Call"),
  activity: __("Activity"),
  meeting: __("Meeting"),
  stage: __("Stage"),
  quotation: __("Quotation"),
  ai: __("TBO AI"),
  proposal: __("Proposal"),
};

/** A call through MyOperator shows which way it went, or that it was missed. */
function timelineIcon(entry: LeadTimelineEntry): Component {
  if (entry.call) {
    if (entry.status === "missed") return LucidePhoneMissed;
    if (entry.direction === "incoming") return LucidePhoneIncoming;
    if (entry.direction === "outgoing") return LucidePhoneOutgoing;
  }
  return TIMELINE_ICONS[entry.kind] || LucideMessageSquare;
}

const showEdit = ref(false);
const showLogCall = ref(false);
const stageFormId = `lead-stage-${useId()}`;

loadLeadOptions();
const options = computed(() => leadOptions.data as LeadOptions | undefined);

const detail = createResource({
  url: "helpdesk.api.leads.get_lead",
  makeParams: () => ({ name: props.leadId }),
  auto: true,
});
watch(
  () => props.leadId,
  () => detail.reload()
);

const data = computed(() => detail.data as LeadDetail | undefined);
const lead = computed(() => data.value?.lead);

const clickToCall = useClickToCall();
const canCall = computed(
  () =>
    !!lead.value?.can_call &&
    !!(lead.value.mobile_no || lead.value.phone || lead.value.whatsapp_no)
);

const detailFields = computed(() => {
  const l = lead.value;
  if (!l) return [];
  const rows: {
    label: string;
    value: string;
    href?: string;
    mono?: boolean;
  }[] = [
    { label: __("Company"), value: l.company_name || "" },
    {
      label: __("Email"),
      value: l.email_id || "",
      href: l.email_id ? `mailto:${l.email_id}` : undefined,
      mono: true,
    },
    {
      label: __("Mobile"),
      value: l.mobile_no || "",
      href: l.mobile_no ? `tel:${l.mobile_no}` : undefined,
      mono: true,
    },
    {
      label: __("Owner"),
      value: l.owner_name || ownerName(options.value, l.lead_owner),
    },
    {
      label: __("Next follow-up"),
      value: l.next_follow_up
        ? dayjs(l.next_follow_up).format("ddd, D MMM YYYY")
        : "",
    },
    { label: __("Source"), value: l.source || "" },
    { label: __("Segment"), value: l.segment || "" },
    { label: __("Territory"), value: l.territory || "" },
    { label: __("Industry"), value: l.industry || "" },
    {
      label: __("Score"),
      value: l.score === null || l.score === undefined ? "" : String(l.score),
      mono: true,
    },
  ];
  return rows.filter((row) => row.value);
});

// --- notes ---

const note = ref("");
const noteError = ref("");

const addNote = createResource({
  url: "helpdesk.api.leads.add_note",
  method: "POST",
  onSuccess() {
    note.value = "";
    toast.success(__("Note added"));
    detail.reload();
  },
  onError(e: unknown) {
    noteError.value = errorText(
      e,
      __("Couldn't add the note. Check your connection and try again.")
    );
  },
});

function submitNote() {
  if (addNote.loading || !note.value.trim()) return;
  noteError.value = "";
  addNote.submit({ name: props.leadId, note: note.value });
}

// --- stage ---

const showStage = ref(false);
const nextStage = ref("");
const stageNote = ref("");
const stageError = ref("");

/** Only the stages the ERP site allows from here. */
const stageChoices = computed<LeadStage[]>(() =>
  (data.value?.allowed_stages ?? [])
    .map((s) =>
      typeof s === "string"
        ? options.value?.stages.find((o) => o.name === s) || { name: s }
        : s
    )
    .filter((s) => s.name !== lead.value?.tbo_stage)
);

function openStageDialog() {
  nextStage.value =
    stageChoices.value.length === 1 ? stageChoices.value[0].name : "";
  stageNote.value = "";
  stageError.value = "";
  showStage.value = true;
}

const setStage = createResource({
  url: "helpdesk.api.leads.set_stage",
  method: "POST",
  onSuccess() {
    toast.success(
      __("Moved to {0}", stageLabel(options.value, nextStage.value))
    );
    showStage.value = false;
    detail.reload();
  },
  onError(e: unknown) {
    stageError.value = errorText(
      e,
      __("Couldn't move the lead. Check your connection and try again.")
    );
  },
});

function submitStage() {
  if (setStage.loading || !nextStage.value) return;
  stageError.value = "";
  setStage.submit({
    name: props.leadId,
    stage: nextStage.value,
    note: stageNote.value.trim() || null,
  });
}
</script>

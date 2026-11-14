<template>
  <div class="flex h-full flex-col">
    <LayoutHeader>
      <template #left-header>
        <router-link
          :to="{ name: 'Leads' }"
          class="inline-flex items-center gap-1.5 rounded text-lg-medium text-ink-gray-7 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
          :aria-label="__('Back to leads')"
        >
          <LucideChevronLeft class="size-4 shrink-0" aria-hidden="true" />
          {{ __("Leads") }}
        </router-link>
      </template>
    </LayoutHeader>

    <!-- who this is, what to do about it, and where it stands -->
    <header
      v-if="lead"
      class="border-b border-outline-gray-2 bg-surface-base"
      :aria-label="__('Lead')"
    >
      <div
        class="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-4 md:px-6"
      >
        <div class="flex flex-wrap items-center gap-x-3 gap-y-2">
          <div class="min-w-0 flex-1 basis-64">
            <p class="truncate text-xs text-ink-gray-6">
              <span class="font-mono tabular-nums">{{ leadId }}</span>
              <template v-if="departmentLabel(lead)">
                · {{ departmentLabel(lead) }}
              </template>
              <template v-if="lead.product"> · {{ lead.product }}</template>
            </p>
            <h1
              class="mt-0.5 truncate text-xl font-semibold text-ink-gray-9"
              :title="lead.lead_name || leadId"
            >
              {{ lead.lead_name || leadId }}
            </h1>
          </div>
          <TaskyBadge
            v-if="temperature"
            :tone="temperature === 'Hot' ? 'warning' : 'neutral'"
            :icon="temperature === 'Hot' ? LucideFlame : undefined"
            :label="temperature"
          />
          <div class="flex flex-wrap items-center gap-2">
            <Button
              v-if="whatsappLink"
              :label="__('WhatsApp')"
              :link="whatsappLink"
              target="_blank"
            >
              <template #prefix>
                <LucideMessageCircle class="size-4" aria-hidden="true" />
              </template>
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
            </Button>
            <Button :label="__('Edit')" @click="showEdit = true">
              <template #prefix>
                <LucidePencil class="size-4" aria-hidden="true" />
              </template>
            </Button>
            <Button
              v-if="canCall"
              variant="solid"
              :label="__('Call')"
              :loading="placing?.lead === leadId"
              :tooltip="__('Rings your phone first, then the lead')"
              @click="callWithMyOperator"
            >
              <template #prefix>
                <LucidePhone class="size-4" aria-hidden="true" />
              </template>
            </Button>
          </div>
        </div>

        <!-- the main path as steps, the side stages in Move to; a step or stage this lead
             may move to opens the Move stage dialog with it picked -->
        <template v-if="stagePath.steps.length">
          <!-- a phone has no room for the steps: the stage, and the dialog to move it -->
          <Button
            class="self-start sm:hidden"
            :disabled="!stageChoices.length"
            @click="openStageDialog()"
          >
            {{ __("Stage: {0}", stageLabel(options, lead.tbo_stage)) }}
            <template #suffix>
              <LucideChevronDown class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <div class="hidden flex-wrap items-center gap-x-3 gap-y-2 sm:flex">
            <!-- at full width, so Move to wraps before the steps scroll; padded so the
                 focus ring isn't clipped where they do -->
            <ol
              class="-m-1 flex min-w-0 flex-auto gap-1 overflow-x-auto p-1"
              :aria-label="__('Stage')"
            >
              <li
                v-for="step in stagePath.steps"
                :key="step.key"
                class="flex-1"
              >
                <button
                  type="button"
                  class="inline-flex h-9 w-full items-center justify-center gap-1.5 whitespace-nowrap rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                  :class="step.class"
                  :aria-disabled="!step.target || undefined"
                  :aria-current="step.current ? 'step' : undefined"
                  :title="step.title"
                  @click="step.target && openStageDialog(step.target)"
                >
                  <LucideCheck
                    v-if="step.done"
                    class="size-4 shrink-0"
                    aria-hidden="true"
                  />
                  {{ step.label }}
                  <span v-if="step.done" class="sr-only">{{
                    __("(done)")
                  }}</span>
                </button>
              </li>
            </ol>
            <p
              v-if="stagePath.side"
              class="flex items-center gap-1.5 text-sm text-ink-gray-6"
            >
              {{ __("Now") }}
              <TaskyBadge
                :label="stageLabel(options, stagePath.side)"
                :tone="stageTone(options, stagePath.side)"
                :icon="stageIcon(stagePath.side)"
              />
            </p>
            <Dropdown :options="sideMenu" align="end">
              <Button
                :label="__('Move to…')"
                :disabled="!sideMenu.length"
                :title="sideMenu.length ? '' : __('No other stage from here')"
              >
                <template #suffix>
                  <LucideChevronDown class="size-4" aria-hidden="true" />
                </template>
              </Button>
            </Dropdown>
          </div>
        </template>
        <Button
          v-else-if="stageChoices.length"
          class="self-start"
          :label="__('Move stage')"
          @click="openStageDialog()"
        />
      </div>
    </header>

    <div class="relative flex-1 overflow-auto">
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
          class="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]"
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

        <div
          v-else
          class="grid grid-cols-1 items-start gap-4 lg:grid-cols-[minmax(0,1fr)_24rem]"
        >
          <LeadDocuments
            class="lg:col-span-2"
            :lead-id="leadId"
            :chain="data.documents"
            :can-write="!!lead?.can_write"
          />

          <!-- the card column comes first on a phone: the numbers are what a call needs -->
          <aside
            class="flex min-w-0 flex-col gap-4 lg:order-2"
            :aria-label="__('Lead details')"
          >
            <LeadDuplicates
              v-if="lead?.can_merge"
              :lead="lead"
              @merged="merged"
            />
            <section
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-label="__('Next step')"
            >
              <h2 class="mb-2 text-base-medium text-ink-gray-9">
                {{ __("Next step") }}
              </h2>
              <p
                v-if="lead?.next_follow_up"
                class="text-base-medium"
                :class="followUpLate ? 'text-danger' : 'text-ink-gray-9'"
              >
                {{ __("Follow up") }}
                <span class="tabular-nums">{{
                  dayjs(lead.next_follow_up).format("ddd, D MMM YYYY")
                }}</span>
                <span v-if="followUpLate" class="font-normal"
                  >· {{ __("overdue") }}</span
                >
              </p>
              <p v-else class="text-p-sm text-ink-gray-6">
                {{ __("No follow-up set. Edit the lead to add one.") }}
              </p>
              <p
                v-if="lead?.owner_name || lead?.lead_owner"
                class="mt-0.5 text-sm text-ink-gray-6"
              >
                {{ lead.owner_name || ownerName(options, lead.lead_owner) }}
              </p>
            </section>
            <section
              v-if="lead?.numbers"
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
            >
              <LeadNumbers
                :lead-id="leadId"
                :lead-name="lead.lead_name || leadId"
                :numbers="lead.numbers"
                :can-write="!!lead.can_write"
                :can-call="!!lead.can_call"
                :can-remove="!!lead.can_remove_numbers"
                :batch-item="batchItem"
                @changed="detail.reload()"
              />
            </section>
            <section
              class="rounded-xl border border-outline-gray-2 bg-surface-base p-4"
              :aria-label="__('Details')"
            >
              <div class="mb-3 flex flex-wrap items-center gap-2">
                <h2 class="text-base-medium text-ink-gray-9">
                  {{ __("Details") }}
                </h2>
                <TaskyBadge
                  v-if="lead && lastCall(lead)"
                  class="ml-auto font-normal tabular-nums"
                  :label="lastCall(lead)!.label"
                  :tone="lastCall(lead)!.tone"
                  :icon="lastCall(lead)!.icon"
                  :title="__('Last call')"
                />
              </div>
              <dl
                class="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-2.5 text-sm"
              >
                <template v-for="field in detailFields" :key="field.label">
                  <dt class="text-ink-gray-6">{{ field.label }}</dt>
                  <dd
                    class="min-w-0 break-words text-ink-gray-8"
                    :class="field.mono ? 'font-mono tabular-nums' : ''"
                  >
                    <a
                      v-if="field.href"
                      :href="field.href"
                      class="rounded underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
                      @click="field.href.startsWith('tel:') && phoneCalled()"
                      >{{ field.value }}</a
                    >
                    <template v-else>{{ field.value }}</template>
                  </dd>
                </template>
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
            <LeadWhyCall :prospect="lead?.prospect" />
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
          </aside>

          <div class="flex min-w-0 flex-col gap-4 lg:order-1">
            <LeadWhatsApp
              v-if="lead?.whatsapp && lead.whatsapp_box"
              :lead-id="leadId"
              :whatsapp="lead.whatsapp"
              :box="lead.whatsapp_box"
              :can-write="!!lead.can_write"
              @sent="detail.reload()"
            />
            <LeadAISuggests
              :lead-id="leadId"
              :last-reply="{
                class: lead?.last_reply_class,
                on: lead?.last_reply_on,
              }"
              @changed="detail.reload()"
            />
            <section
              class="min-w-0 rounded-xl border border-outline-gray-2 bg-surface-base px-4 py-4 sm:px-5"
              :aria-label="__('Timeline')"
            >
              <div class="mb-3 flex items-baseline gap-2">
                <h2 class="text-base-medium text-ink-gray-9">
                  {{ __("Activity") }}
                </h2>
                <span class="text-sm text-ink-gray-6">{{
                  __("newest first")
                }}</span>
              </div>
              <form
                class="flex items-start gap-2 pb-2"
                @submit.prevent="submitNote"
              >
                <FormControl
                  v-model="note"
                  class="min-w-0 flex-1"
                  type="textarea"
                  :rows="2"
                  :aria-label="__('Add a note')"
                  :placeholder="
                    __(
                      'Add a note: what was said, what was agreed, what\'s next'
                    )
                  "
                />
                <Button
                  type="submit"
                  :label="__('Add note')"
                  :loading="addNote.loading"
                  :disabled="!note.trim()"
                />
              </form>
              <p
                v-if="noteError"
                role="alert"
                class="pb-2 text-p-sm text-danger"
              >
                {{ noteError }}
              </p>
              <p
                v-if="!data.timeline?.length"
                class="border-t border-outline-gray-1 py-6 text-p-sm text-ink-gray-6"
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
                  class="flex gap-3 border-t border-outline-gray-1 py-3.5"
                >
                  <span
                    class="grid size-8 shrink-0 place-items-center rounded-full"
                    :class="
                      entry.call && entry.status === 'missed'
                        ? 'bg-danger-soft text-danger'
                        : entry.call && entry.status === 'answered'
                        ? 'bg-success-soft text-success'
                        : 'bg-surface-gray-2 text-ink-gray-7'
                    "
                    aria-hidden="true"
                  >
                    <component :is="timelineIcon(entry)" class="size-4" />
                  </span>
                  <div class="flex min-w-0 flex-1 flex-col gap-1">
                    <div class="flex flex-wrap items-baseline gap-x-2">
                      <span
                        v-if="!entry.call"
                        class="text-base-medium text-ink-gray-9"
                        >{{ TIMELINE_LABELS[entry.kind] }}</span
                      >
                      <span class="text-sm text-ink-gray-6">{{
                        entry.kind === "whatsapp" &&
                        entry.direction === "incoming"
                          ? __("The lead, on WhatsApp")
                          : entry.who_name || entry.who
                      }}</span>
                      <time
                        v-if="entry.at"
                        class="ml-auto font-mono text-xs tabular-nums text-ink-gray-6"
                        :datetime="entry.at"
                        :title="dayjs(entry.at).format('D MMM YYYY, h:mm a')"
                        >{{ dayjs(entry.at).fromNow() }}</time
                      >
                    </div>
                    <LeadCallEntry v-if="entry.call" :entry="entry" />
                    <p
                      v-else-if="entry.text"
                      class="whitespace-pre-line break-words text-p-sm text-ink-gray-8"
                    >
                      {{ entry.text }}
                    </p>
                  </div>
                </li>
              </ol>
            </section>
          </div>
        </div>
      </div>
    </div>

    <LogCallDialog
      v-model:open="showLogCall"
      :lead-id="leadId"
      :numbers="(lead?.numbers ?? []).filter(isUsable)"
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
            <component
              :is="stageIcon(stage.name)"
              v-if="stageIcon(stage.name)"
              class="size-4 shrink-0"
              :class="INK[stageTone(options, stage.name)]"
              aria-hidden="true"
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
import { INK } from "@/components/tone";
import TaskyState from "@/components/TaskyState.vue";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import {
  Button,
  createResource,
  dayjs,
  Dialog,
  Dropdown,
  FormControl,
  toast,
} from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import { useRoute, useRouter } from "vue-router";
import LucideArrowRight from "~icons/lucide/arrow-right";
import LucideBot from "~icons/lucide/bot";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCheck from "~icons/lucide/check";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideChevronLeft from "~icons/lucide/chevron-left";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideFileText from "~icons/lucide/file-text";
import LucideFlame from "~icons/lucide/flame";
import LucideHistory from "~icons/lucide/history";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucideMessageCircleReply from "~icons/lucide/message-circle-reply";
import LucideMessageSquare from "~icons/lucide/message-square";
import LucidePhone from "~icons/lucide/phone";
import LucidePhoneForwarded from "~icons/lucide/phone-forwarded";
import LucidePhoneIncoming from "~icons/lucide/phone-incoming";
import LucidePhoneMissed from "~icons/lucide/phone-missed";
import LucidePhoneOutgoing from "~icons/lucide/phone-outgoing";
import LucidePencil from "~icons/lucide/pencil";
import LeadAISuggests from "./LeadAISuggests.vue";
import LeadNumbers from "./LeadNumbers.vue";
import LeadCallEntry from "./LeadCallEntry.vue";
import LucideScrollText from "~icons/lucide/scroll-text";
import LeadFormDialog from "./LeadFormDialog.vue";
import LeadPhotos from "./LeadPhotos.vue";
import LeadPlace from "./LeadPlace.vue";
import LeadWhatsApp from "./LeadWhatsApp.vue";
import LeadWhyCall from "./LeadWhyCall.vue";
import LeadDocuments from "./LeadDocuments.vue";
import LeadDuplicates from "./LeadDuplicates.vue";
import LogCallDialog from "./LogCallDialog.vue";
import LeadProposals from "./LeadProposals.vue";
import LeadQuotations from "./LeadQuotations.vue";
import {
  departmentLabel,
  dropUnsavedNote,
  loadLeadOptions,
  leadOptions,
  ownerName,
  lastCall,
  stageIcon,
  stageLabel,
  isUsable,
  stageTone,
  STAGE_PATH,
  unsavedNote,
  type LeadDetail,
  type LeadOptions,
  type LeadStage,
  type LeadTimelineEntry,
} from "./leads";
import { placeCall, placing } from "./callBox";
import { queueChanged, startCall } from "./pendingCalls";

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
  whatsapp: LucideMessageCircle,
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
  whatsapp: __("WhatsApp"),
};

/** A call through MyOperator shows which way it went, or that it was missed. */
function timelineIcon(entry: LeadTimelineEntry): Component {
  if (entry.call) {
    if (entry.status === "missed") return LucidePhoneMissed;
    if (entry.direction === "incoming") return LucidePhoneIncoming;
    if (entry.direction === "outgoing") return LucidePhoneOutgoing;
  }
  if (entry.kind === "whatsapp" && entry.direction === "outgoing")
    return LucideMessageCircleReply;
  return TIMELINE_ICONS[entry.kind] || LucideMessageSquare;
}

const router = useRouter();
const route = useRoute();

/** Opened from Today's calls: the call there it belongs to, so its result counts in the
 * batch. Once a result is recorded it is done, and a later call here is an ordinary one. */
const batchItem = computed(() =>
  typeof route.query.item === "string" ? route.query.item : null
);
watch(queueChanged, () => {
  if (batchItem.value) router.replace({ query: {} });
});

/** After a merge the lead that was kept is the one to see (the merged one is gone). */
function merged(keep: string) {
  if (keep !== props.leadId) {
    router.replace({ name: "Lead", params: { leadId: keep } });
  } else {
    detail.reload();
  }
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

const leadName = computed(() => lead.value?.lead_name || props.leadId);
const leadPhone = computed(
  () => lead.value?.mobile_no || lead.value?.phone || ""
);

/** The call box rings the person's phone, then the lead. */
function callWithMyOperator() {
  placeCall({
    lead: props.leadId,
    lead_name: leadName.value,
    company: lead.value?.company_name,
    phone: leadPhone.value,
    number: null,
    // opened from Today's calls: the result counts in that batch
    item: batchItem.value,
    product: lead.value?.product,
  });
}
/** A call from the phone's own dialler waits for its result: the sheet asks how it went. */
function phoneCalled() {
  startCall({
    lead: props.leadId,
    lead_name: leadName.value,
    phone: leadPhone.value,
    number: lead.value?.mobile_no || null,
    item: batchItem.value,
    via: "phone",
  });
}
const canCall = computed(
  () =>
    !!lead.value?.can_call &&
    !!(lead.value.mobile_no || lead.value.phone || lead.value.whatsapp_no)
);

/** Hot or Warm, when the ERP site's lead says so. */
const temperature = computed(() => {
  const value = lead.value?.temperature;
  return typeof value === "string" ? value : "";
});
const whatsappLink = computed(() => {
  const digits = String(
    lead.value?.whatsapp_no || lead.value?.mobile_no || ""
  ).replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : "";
});
const followUpLate = computed(
  () =>
    !!lead.value?.next_follow_up &&
    dayjs(lead.value.next_follow_up).isBefore(dayjs().startOf("day"))
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
    // an older TBO Smart sends one number; with the list of numbers it shows above
    {
      label: __("Mobile"),
      value: l.numbers ? "" : l.mobile_no || "",
      href: l.mobile_no ? `tel:${l.mobile_no}` : undefined,
      mono: true,
    },
    {
      label: __("Owner"),
      value: l.owner_name || ownerName(options.value, l.lead_owner),
    },
    { label: __("Source"), value: l.source || "" },
    { label: __("Segment"), value: l.segment || "" },
    { label: __("Territory"), value: l.territory || "" },
    { label: __("Product"), value: l.product || "" },
    { label: __("Industry"), value: l.industry || "" },
    { label: __("State"), value: l.state || "" },
    { label: __("District"), value: l.district || "" },
    { label: __("Organisation size"), value: l.org_size || "" },
    {
      label: __("Score"),
      value: l.score === null || l.score === undefined ? "" : String(l.score),
      mono: true,
    },
  ];
  return rows.filter((row) => row.value);
});

// --- notes ---

// starts with the remarks the New lead dialog couldn't save, kept until they're added
const note = ref(unsavedNote(props.leadId));
// whether the box holds those remarks (edited or not) rather than a note started afresh
const fromDraft = ref(!!note.value);
const noteError = ref("");
watch(
  () => props.leadId,
  (lead) => {
    note.value = unsavedNote(lead);
    fromDraft.value = !!note.value;
  }
);
watch(note, (text) => {
  if (!text.trim()) fromDraft.value = false;
});
let draftSent = false;

const addNote = createResource({
  url: "helpdesk.api.leads.add_note",
  method: "POST",
  onSuccess() {
    const { name, note: sent } = addNote.params;
    if (draftSent) dropUnsavedNote(name);
    toast.success(__("Note added"));
    // moved to another lead, or typed on, while it was sent: that text isn't this note
    if (name !== props.leadId) return;
    if (note.value === sent) note.value = "";
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
  draftSent = fromDraft.value;
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

/** The main path (STAGE_PATH) as steps, done ones before the current, and the side stage
 * the lead is in, if it's off the path. A step moves the lead to its first stage the ERP
 * site allows from here; the current step only to a later one (the next meeting). */
const stagePath = computed(() => {
  const known = new Set((options.value?.stages ?? []).map((st) => st.name));
  const allowed = new Set(stageChoices.value.map((st) => st.name));
  const now = lead.value?.tbo_stage || "";
  const path = STAGE_PATH.map((step) => ({
    ...step,
    stages: step.stages.filter((name) => known.has(name)),
  })).filter((step) => step.stages.length);
  const at = path.findIndex((step) => step.stages.includes(now));
  const steps = path.map((step, i) => {
    const current = i === at;
    const from = current ? step.stages.indexOf(now) + 1 : 0;
    const target = step.stages.slice(from).find((name) => allowed.has(name));
    const label =
      current && step.label
        ? stageLabel(options.value, now)
        : step.label || stageLabel(options.value, step.stages[0]);
    return {
      key: step.stages[0],
      label,
      current,
      done: i < at,
      target,
      title: target
        ? __("Move to {0}", stageLabel(options.value, target))
        : current
        ? ""
        : __("This lead can't move to {0} from here.", label),
      class: [
        current
          ? "bg-brand text-brand-on"
          : i < at
          ? "bg-brand-soft text-brand-ink"
          : "bg-surface-gray-2 text-ink-gray-8",
        target
          ? current
            ? "hover:bg-brand-hover"
            : "hover:bg-surface-gray-3"
          : current
          ? "cursor-default"
          : "cursor-default opacity-60",
      ],
    };
  });
  return { steps, side: at === -1 ? now : "" };
});

/** Move to: the side stages the ERP site allows from here. */
const sideMenu = computed(() => {
  const onPath = new Set(STAGE_PATH.flatMap((step) => step.stages));
  return stageChoices.value
    .filter((st) => !onPath.has(st.name))
    .map((st) => ({
      label: st.label || st.name,
      icon: stageIcon(st.name),
      onClick: () => openStageDialog(st.name),
    }));
});

function openStageDialog(preselect?: string) {
  nextStage.value =
    preselect ||
    (stageChoices.value.length === 1 ? stageChoices.value[0].name : "");
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

<template>
  <!-- what the AI proposes for this lead; a person applies, edits and sends (docs/leads.md) -->
  <section
    class="rounded-xl border border-outline-gray-2 bg-surface-base"
    :aria-labelledby="titleId"
  >
    <header
      class="flex flex-wrap items-center gap-2 border-b border-outline-gray-1 px-4 py-3"
    >
      <h2 :id="titleId" class="text-base-medium text-ink-gray-9">
        {{ ai?.enabled ? __("AI suggests") : __("Lead health") }}
      </h2>
      <span
        v-if="ai?.enabled && ai.at"
        class="text-xs text-ink-gray-5"
        :title="dayjs(ai.at).format('D MMM YYYY, h:mm a')"
      >
        {{
          ai.stale
            ? __("Read {0}, before the latest changes", dayjs(ai.at).fromNow())
            : __("Read {0}", dayjs(ai.at).fromNow())
        }}
      </span>
      <Button
        v-if="ai?.enabled && ai.open && ai.ai_ready"
        class="ml-auto"
        variant="ghost"
        :loading="refresh.loading"
        :aria-label="__('Read the lead again')"
        :tooltip="__('Read the lead again')"
        @click="refresh.submit({ name: leadId })"
      >
        <template #icon>
          <LucideRefreshCw class="size-4" aria-hidden="true" />
        </template>
      </Button>
    </header>

    <div
      v-if="!ai && suggestions.loading"
      class="flex flex-col gap-2 px-4 py-4"
      aria-busy="true"
      :aria-label="__('Loading')"
    >
      <div class="h-3.5 w-3/4 animate-pulse rounded bg-surface-gray-2" />
      <div class="h-3 w-1/2 animate-pulse rounded bg-surface-gray-2" />
    </div>

    <div
      v-else-if="!ai && suggestions.error"
      role="alert"
      class="flex flex-col items-start gap-2 px-4 py-4"
    >
      <p class="text-p-sm text-ink-gray-7">
        {{
          errorText(
            suggestions.error,
            __("Couldn't load what the AI suggests.")
          )
        }}
      </p>
      <Button :label="__('Try again')" @click="suggestions.reload()" />
    </div>

    <div v-else-if="ai" class="flex flex-col divide-y divide-outline-gray-1">
      <p
        v-if="actionError"
        role="alert"
        class="px-4 py-3 text-p-sm text-danger"
      >
        {{ actionError }}
      </p>

      <!-- the AI's read -->
      <template v-if="ai.enabled && ai.open">
        <div v-if="!insight" class="flex flex-col items-start gap-2 px-4 py-4">
          <p class="text-p-sm text-ink-gray-6">
            {{
              ai.ai_ready
                ? __(
                    "The AI reads a lead when it changes. It hasn't read this one yet."
                  )
                : __(
                    "The AI isn't set up on the ERP site yet. Ask an admin to add a provider in TBO Smart Settings."
                  )
            }}
          </p>
          <Button
            v-if="ai.ai_ready"
            :label="__('Read it now')"
            :loading="refresh.loading"
            @click="refresh.submit({ name: leadId })"
          />
        </div>

        <template v-else>
          <div class="flex flex-col gap-2 px-4 py-3">
            <p v-if="insight.summary" class="text-p-sm text-ink-gray-8">
              {{ insight.summary }}
            </p>
            <div class="flex flex-wrap gap-1.5">
              <TaskyBadge
                :label="__('Sentiment: {0}', __(insight.sentiment))"
                :tone="insight.sentiment === 'Negative' ? 'warning' : 'neutral'"
                :icon="SENTIMENT_ICONS[insight.sentiment]"
              />
              <TaskyBadge
                :label="__('Intent: {0}', __(insight.intent))"
                :icon="LucideTarget"
              />
            </div>
            <ul
              v-if="insight.signals.length"
              class="flex flex-col gap-0.5 text-xs text-ink-gray-6"
              :aria-label="__('What shows it')"
            >
              <li v-for="signal in insight.signals" :key="signal">
                “{{ signal }}”
              </li>
            </ul>
          </div>

          <!-- the next best action, already the follow-up when nothing else was planned -->
          <div v-if="insight.next_action" class="flex gap-3 px-4 py-3">
            <component
              :is="CHANNEL_ICONS[insight.next_action.channel]"
              class="mt-0.5 size-4 shrink-0 text-ink-gray-5"
              aria-hidden="true"
            />
            <div class="flex min-w-0 flex-col gap-0.5">
              <span class="text-xs text-ink-gray-5">{{
                __("Next step, by {0}", dueText(insight.next_action.due))
              }}</span>
              <span class="text-base-medium text-ink-gray-9">{{
                insight.next_action.what
              }}</span>
              <span
                v-if="insight.next_action.why"
                class="text-p-sm text-ink-gray-6"
                >{{ insight.next_action.why }}</span
              >
            </div>
          </div>

          <!-- a stage to move to: only a person moves it -->
          <div
            v-if="insight.suggested_stage"
            class="flex flex-col gap-2 px-4 py-3"
          >
            <p class="text-p-sm text-ink-gray-8">
              {{ __("Move to {0}?", insight.suggested_stage) }}
              <span v-if="insight.stage_reason" class="text-ink-gray-6">
                {{ insight.stage_reason }}</span
              >
            </p>
            <div class="flex flex-wrap gap-2">
              <Button
                :label="__('Move to {0}', insight.suggested_stage)"
                :loading="applyStage.loading"
                @click="applyStage.submit({ name: leadId })"
              />
              <Button
                variant="ghost"
                :label="__('Dismiss')"
                :loading="dismissStage.loading"
                @click="dismissStage.submit({ name: leadId })"
              />
            </div>
          </div>
        </template>

        <!-- a message to send: edited and sent by the person, from their own app -->
        <div class="flex flex-col gap-2 px-4 py-3">
          <template v-if="draft">
            <FormControl
              v-if="draft.channel === 'email'"
              v-model="draft.subject"
              :label="__('Subject')"
            />
            <FormControl
              v-model="draft.text"
              type="textarea"
              :rows="5"
              :label="
                draft.channel === 'email'
                  ? __('Email to send')
                  : __('WhatsApp message to send')
              "
              :description="
                __(
                  'Nothing is sent from here. Check it, open your WhatsApp or mail, and press Send there.'
                )
              "
            />
            <div class="flex flex-wrap gap-2">
              <Button
                v-if="sendLink"
                :label="
                  draft.channel === 'email'
                    ? __('Open in mail')
                    : __('Open in WhatsApp')
                "
                :link="sendLink"
                @click="opened = true"
              >
                <template #suffix>
                  <LucideExternalLink class="size-4" aria-hidden="true" />
                </template>
              </Button>
              <Button
                v-if="opened"
                :label="__('I sent it')"
                :loading="logSent.loading"
                @click="
                  logSent.submit({
                    name: leadId,
                    channel: draft.channel,
                    text: draft.text,
                  })
                "
              />
              <Button
                variant="ghost"
                :label="__('Discard')"
                @click="discardDraft"
              />
            </div>
            <p v-if="!sendLink" class="text-p-sm text-ink-gray-6">
              {{
                draft.channel === "email"
                  ? __("This lead has no email address. Add one with Edit.")
                  : __("This lead has no mobile number. Add one with Edit.")
              }}
            </p>
          </template>
          <div v-else class="flex flex-wrap items-center gap-2">
            <span class="text-p-sm text-ink-gray-6">{{
              __("Draft a message")
            }}</span>
            <Button
              :label="__('WhatsApp')"
              :loading="newDraft.loading && wanted === 'whatsapp'"
              :disabled="newDraft.loading"
              @click="draftNew('whatsapp')"
            />
            <Button
              :label="__('Email')"
              :loading="newDraft.loading && wanted === 'email'"
              :disabled="newDraft.loading"
              @click="draftNew('email')"
            />
          </div>
        </div>
      </template>

      <!-- rules, not AI: shown with AI runs leads off too -->
      <div v-if="ai.health" class="flex flex-col gap-1.5 px-4 py-3">
        <TaskyBadge
          class="self-start"
          :label="HEALTH[ai.health.status].label"
          :tone="HEALTH[ai.health.status].tone"
          :icon="HEALTH[ai.health.status].icon"
        />
        <ul
          v-if="ai.health.signals.length"
          class="flex flex-col gap-0.5 text-p-sm text-ink-gray-7"
        >
          <li v-for="signal in ai.health.signals" :key="signal.key">
            {{ signal.text }}
          </li>
        </ul>
      </div>

      <div v-if="ai.duplicates.length" class="flex flex-col gap-1.5 px-4 py-3">
        <h3 class="text-xs text-ink-gray-5">
          {{ __("Maybe the same customer") }}
        </h3>
        <ul class="flex flex-col gap-1">
          <li v-for="dupe in ai.duplicates" :key="dupe.name">
            <router-link
              :to="{ name: 'Lead', params: { leadId: dupe.name } }"
              class="flex flex-col rounded px-1 py-0.5 hover:bg-surface-gray-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-outline-gray-4"
            >
              <span class="truncate text-sm text-ink-gray-9">{{
                dupe.lead_name || dupe.name
              }}</span>
              <span class="truncate text-xs text-ink-gray-6">
                {{
                  [
                    __("Same {0}", dupe.match.map((m) => MATCH[m]).join(", ")),
                    dupe.tbo_stage,
                    dupe.owner_name,
                  ]
                    .filter(Boolean)
                    .join(" · ")
                }}
              </span>
            </router-link>
          </li>
        </ul>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import type { Tone } from "@/components/tone";
import { __ } from "@/translation";
import { errorText } from "@/utils";
import { Button, createResource, dayjs, FormControl, toast } from "frappe-ui";
import { computed, ref, useId, watch, type Component } from "vue";
import LucideCalendar from "~icons/lucide/calendar";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideCircleCheck from "~icons/lucide/circle-check";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideFrown from "~icons/lucide/frown";
import LucideMail from "~icons/lucide/mail";
import LucideMeh from "~icons/lucide/meh";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucidePhone from "~icons/lucide/phone";
import LucideRefreshCw from "~icons/lucide/refresh-cw";
import LucideSmile from "~icons/lucide/smile";
import LucideTarget from "~icons/lucide/target";
import LucideTriangleAlert from "~icons/lucide/triangle-alert";
import type { LeadAI, LeadDraft } from "./leads";

const props = defineProps<{ leadId: string }>();
/** the lead changed here (a stage applied, a message logged): reload it */
const emit = defineEmits<{ changed: [] }>();

const titleId = useId();
const SENTIMENT_ICONS: Record<string, Component> = {
  Positive: LucideSmile,
  Neutral: LucideMeh,
  Negative: LucideFrown,
};
const CHANNEL_ICONS: Record<string, Component> = {
  call: LucidePhone,
  whatsapp: LucideMessageCircle,
  email: LucideMail,
  meeting: LucideCalendar,
};
const HEALTH: Record<string, { label: string; tone: Tone; icon: Component }> = {
  healthy: {
    label: __("Healthy"),
    tone: "success",
    icon: LucideCircleCheck,
  },
  watch: {
    label: __("Watch"),
    tone: "warning",
    icon: LucideTriangleAlert,
  },
  at_risk: {
    label: __("At risk"),
    tone: "danger",
    icon: LucideCircleAlert,
  },
};
const MATCH: Record<string, string> = {
  phone: __("phone"),
  email: __("email"),
  company: __("company"),
};

const actionError = ref("");
const draft = ref<LeadDraft | null>(null);
const opened = ref(false);
const wanted = ref<"whatsapp" | "email">("whatsapp");
const storedTaken = ref(false);

const suggestions = createResource({
  url: "helpdesk.api.leads.get_lead_ai",
  makeParams: () => ({ name: props.leadId }),
  auto: true,
});
watch(
  () => props.leadId,
  () => {
    // the old lead's suggestions must never show (or be acted on) under the new one
    draft.value = null;
    opened.value = false;
    actionError.value = "";
    storedTaken.value = false;
    suggestions.reset();
    suggestions.reload();
  }
);

const ai = computed(() => suggestions.data as LeadAI | undefined);
const insight = computed(() => ai.value?.insight ?? null);

// the stored draft is offered once per AI read: after Discard or "I sent it" it
// never comes back with a reload, so nobody sends it twice
watch(
  () => insight.value?.message,
  (message) => {
    if (message && !draft.value && !storedTaken.value) {
      storedTaken.value = true;
      draft.value = {
        channel: message.channel,
        subject: message.subject || "",
        text: message.text,
      };
    }
  },
  { immediate: true }
);

function onError(error: unknown) {
  actionError.value = errorText(error, __("That didn't work. Try again."));
}

function took(data: LeadAI) {
  actionError.value = "";
  suggestions.setData(data);
}

const refresh = createResource({
  url: "helpdesk.api.leads.refresh_lead_ai",
  onSuccess: (data: LeadAI) => {
    draft.value = null;
    storedTaken.value = false;
    took(data);
  },
  onError,
});

const applyStage = createResource({
  url: "helpdesk.api.leads.apply_ai_stage",
  onSuccess() {
    actionError.value = "";
    toast.success(__("Stage moved"));
    suggestions.reload();
    emit("changed");
  },
  onError,
});

const dismissStage = createResource({
  url: "helpdesk.api.leads.dismiss_ai_stage",
  onSuccess: took,
  onError,
});

const newDraft = createResource({
  url: "helpdesk.api.leads.draft_lead_message",
  onSuccess(data: LeadDraft) {
    actionError.value = "";
    opened.value = false;
    draft.value = { ...data, subject: data.subject || "" };
  },
  onError,
});

function draftNew(channel: "whatsapp" | "email") {
  wanted.value = channel;
  newDraft.submit({ name: props.leadId, channel });
}

const logSent = createResource({
  url: "helpdesk.api.leads.log_message_sent",
  onSuccess() {
    toast.success(__("Logged on the lead"));
    discardDraft();
    emit("changed");
  },
  onError,
});

function discardDraft() {
  draft.value = null;
  opened.value = false;
}

// the person's own WhatsApp or mail app, with the edited text
const sendLink = computed(() => {
  const d = draft.value;
  const contact = ai.value?.contact;
  if (!d) return "";
  if (d.channel === "whatsapp")
    return contact?.whatsapp
      ? `https://wa.me/${contact.whatsapp}?text=${encodeURIComponent(d.text)}`
      : "";
  const to = d.to || contact?.email;
  return to
    ? `mailto:${to}?subject=${encodeURIComponent(
        d.subject || ""
      )}&body=${encodeURIComponent(d.text)}`
    : "";
});

function dueText(day: string) {
  const d = dayjs(day);
  if (d.isSame(dayjs(), "day")) return __("today");
  if (d.isSame(dayjs().add(1, "day"), "day")) return __("tomorrow");
  return d.format("D MMM");
}
</script>

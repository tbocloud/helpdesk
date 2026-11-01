<template>
  <li class="border-b border-outline-gray-1 last:border-b-0">
    <div class="flex items-start gap-3 px-4 py-3">
      <Checkbox
        v-if="selectable"
        class="mt-0.5 shrink-0"
        :model-value="selected"
        :label="__('Select {0}', message.lead_name || message.lead)"
        @update:model-value="emit('toggle')"
      />
      <button
        type="button"
        class="flex min-w-0 flex-1 items-start gap-3 rounded text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
        :aria-expanded="open"
        :aria-controls="panelId"
        @click="open = !open"
      >
        <component
          :is="message.channel === 'Email' ? LucideMail : LucideMessageCircle"
          class="mt-0.5 size-4 shrink-0 text-ink-gray-6"
          :aria-label="
            message.channel === 'Email' ? __('Email') : __('WhatsApp')
          "
          role="img"
        />
        <span class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="flex min-w-0 flex-wrap items-center gap-2">
            <span class="truncate text-base-medium text-ink-gray-9">{{
              message.company_name || message.lead_name || message.lead
            }}</span>
            <TaskyBadge
              :label="statusLabel"
              :tone="STATUS_LOOK[message.status].tone"
              :icon="STATUS_LOOK[message.status].icon"
            />
            <TaskyBadge
              v-if="message.last_reply_class"
              :label="REPLY_LOOK[message.last_reply_class].label"
              :tone="REPLY_LOOK[message.last_reply_class].tone"
              :icon="REPLY_LOOK[message.last_reply_class].icon"
            />
          </span>
          <span class="truncate text-p-sm text-ink-gray-7">{{
            message.channel === "Email" && message.subject
              ? message.subject
              : message.body
          }}</span>
          <span class="flex flex-wrap gap-x-3 text-xs text-ink-gray-5">
            <span v-if="message.recipient" class="font-mono">{{
              message.recipient
            }}</span>
            <span v-if="showOwner && message.owner_name">{{
              message.owner_name
            }}</span>
            <span :title="dayjs(when).format('D MMM YYYY, h:mm a')">{{
              dayjs(when).fromNow()
            }}</span>
          </span>
        </span>
        <LucideChevronDown
          class="mt-0.5 size-4 shrink-0 text-ink-gray-5 transition-transform"
          :class="open ? 'rotate-180' : ''"
          aria-hidden="true"
        />
      </button>
      <!-- WhatsApp has no API: the person sends it themselves, then says so -->
      <div
        v-if="message.channel === 'WhatsApp' && message.status === 'Approved'"
        class="flex shrink-0 flex-wrap justify-end gap-2"
      >
        <Button
          v-if="message.url"
          :label="__('Open WhatsApp')"
          @click="openWhatsApp"
        >
          <template #prefix>
            <LucideExternalLink class="size-4" aria-hidden="true" />
          </template>
        </Button>
        <Button
          variant="solid"
          :label="__('Mark sent')"
          :loading="busy"
          @click="emit('mark-sent')"
        />
      </div>
    </div>

    <div
      v-if="open"
      :id="panelId"
      class="flex flex-col gap-3 border-t border-outline-gray-1 bg-surface-gray-1 px-4 py-3 md:pl-11"
    >
      <p
        v-if="message.error"
        role="alert"
        class="flex items-start gap-2 text-p-sm text-ink-gray-9"
      >
        <LucideCircleAlert
          class="mt-0.5 size-4 shrink-0 text-danger"
          aria-hidden="true"
        />
        {{ message.error }}
      </p>
      <p
        v-if="message.unsubscribed && message.status === 'Draft'"
        class="text-p-sm text-ink-gray-7"
      >
        {{ __("This lead unsubscribed, so this message will not go out.") }}
      </p>

      <template v-if="editable">
        <FormControl
          v-if="message.channel === 'Email'"
          v-model="subject"
          type="text"
          :label="__('Subject')"
        />
        <FormControl
          v-model="body"
          type="textarea"
          :rows="6"
          :label="__('Message')"
        />
        <p
          v-if="message.channel === 'Email' && optOut"
          class="text-xs text-ink-gray-6"
        >
          {{ __("Added under every email when it is sent:") }} “{{ optOut }}”
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <Button
            v-if="message.status === 'Draft'"
            variant="solid"
            :label="__('Approve')"
            :loading="busy"
            :disabled="!canApprove"
            @click="emit('approve', edits)"
          />
          <Button
            v-if="dirty"
            :label="
              message.status === 'Failed'
                ? __('Save to retry')
                : __('Save changes')
            "
            :loading="busy"
            @click="emit('save', edits)"
          />
          <Button
            :label="__('Regenerate')"
            :loading="busy"
            @click="emit('regenerate')"
          >
            <template #prefix>
              <LucideRotateCw class="size-4" aria-hidden="true" />
            </template>
          </Button>
          <Button
            variant="ghost"
            :label="__('Cancel message')"
            :loading="busy"
            @click="emit('cancel')"
          />
          <router-link
            :to="{ name: 'Lead', params: { leadId: message.lead } }"
            class="ml-auto rounded text-p-sm text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Open the lead") }}</router-link
          >
        </div>
      </template>

      <template v-else>
        <p
          v-if="message.channel === 'Email' && message.subject"
          class="text-base-medium text-ink-gray-9"
        >
          {{ message.subject }}
        </p>
        <p class="whitespace-pre-wrap text-p-sm text-ink-gray-8">
          {{ message.body }}
        </p>
        <p class="flex flex-wrap items-center gap-x-4 text-xs text-ink-gray-5">
          <span v-if="message.approved_by">{{
            __("Approved by {0}", message.approved_by)
          }}</span>
          <span v-if="message.sent_on">{{
            __("Sent {0}", dayjs(message.sent_on).format("D MMM YYYY, h:mm a"))
          }}</span>
          <router-link
            :to="{ name: 'Lead', params: { leadId: message.lead } }"
            class="rounded text-ink-gray-8 underline decoration-outline-gray-3 underline-offset-2 hover:text-ink-gray-9 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-highlight"
            >{{ __("Open the lead") }}</router-link
          >
          <Button
            v-if="message.status === 'Approved'"
            variant="ghost"
            :label="__('Cancel message')"
            :loading="busy"
            @click="emit('cancel')"
          />
        </p>
      </template>
    </div>
  </li>
</template>

<script setup lang="ts">
import TaskyBadge from "@/components/TaskyBadge.vue";
import { __ } from "@/translation";
import { Button, Checkbox, dayjs, FormControl } from "frappe-ui";
import { computed, ref, useId, watch } from "vue";
import LucideChevronDown from "~icons/lucide/chevron-down";
import LucideCircleAlert from "~icons/lucide/circle-alert";
import LucideExternalLink from "~icons/lucide/external-link";
import LucideMail from "~icons/lucide/mail";
import LucideMessageCircle from "~icons/lucide/message-circle";
import LucideRotateCw from "~icons/lucide/rotate-cw";
import {
  approvedLabel,
  REPLY_LOOK,
  STATUS_LOOK,
  type OutreachMessage,
} from "./outreach";

const props = defineProps<{
  message: OutreachMessage;
  selected: boolean;
  /** drafts, approved and failed messages can be picked for Approve or Cancel */
  selectable: boolean;
  /** a department head or manager sees other people's messages: say whose */
  showOwner: boolean;
  /** the line added under every email */
  optOut: string;
  busy: boolean;
}>();
const emit = defineEmits<{
  toggle: [];
  save: [edits: { subject: string; body: string }];
  approve: [edits: { subject: string; body: string }];
  regenerate: [];
  cancel: [];
  "mark-sent": [];
}>();

const panelId = `outreach-${useId()}`;
const open = ref(false);
const subject = ref(props.message.subject || "");
const body = ref(props.message.body);
// an edit made elsewhere (Regenerate, a reload) replaces what is shown, unless the person is typing
watch(
  () => [props.message.subject, props.message.body] as const,
  ([newSubject, newBody]) => {
    subject.value = newSubject || "";
    body.value = newBody;
  }
);

const editable = computed(
  () => props.message.status === "Draft" || props.message.status === "Failed"
);
const edits = computed(() => ({
  subject: subject.value.trim(),
  body: body.value.trim(),
}));
const dirty = computed(
  () =>
    edits.value.body !== props.message.body.trim() ||
    (props.message.channel === "Email" &&
      edits.value.subject !== (props.message.subject || "").trim())
);
const canApprove = computed(
  () =>
    !!edits.value.body &&
    (props.message.channel !== "Email" || !!edits.value.subject) &&
    !props.message.unsubscribed
);
const statusLabel = computed(() =>
  props.message.status === "Approved"
    ? approvedLabel(props.message)
    : STATUS_LOOK[props.message.status].label
);
const when = computed(
  () =>
    props.message.sent_on || props.message.approved_on || props.message.creation
);

function openWhatsApp() {
  window.open(props.message.url!, "_blank", "noopener");
}
</script>
